"""Load one upstream aggregates file after the run loader (Work item 37).

    uv run python cli/load_aggregates.py --label candidate --dir /path/to/candidate_y2
    uv run python cli/load_aggregates.py --label candidate --dir /path/to/candidate_y2 --check-store
    uv run python cli/load_aggregates.py --label candidate --dir /path/to/candidate_y2 --write

The command belongs to the same folder as ``aggregates_<label>.json``, its ``SHA256SUMS`` manifest
and the ``<label>_<window>.db`` databases. A dry run (the default) contacts no store: it verifies
the file's manifest entry and SHA-256, parses it through the whitelist, verifies it read-only
against the source databases, builds the deterministic batch and validates it with
``gate.validate``. ``--check-store`` runs the real gate's ``plan`` (``SELECT`` only, no write) and,
when the graph already exists, checks its stored rows against the file. ``--write`` plans and writes
the one append-only graph ``urn:graph:derived:backtest:aggregates:{label}``, then runs the same
stored-row check. Writing to the production repository also needs ``--to-production``.

Exit status: 0 all requested steps passed; 1 a manifest/file/parser/verifier/gate/store failure; 2
a bad argument or an impossible flag combination.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from kg_store import gate
from kg_store.graphdb import PRODUCTION_REPOSITORY, GraphDB, GraphDBError, announce_target
from projection.aggregates import (
    AggregatesError,
    AggregatesFile,
    Check,
    Verification,
    graph_name,
    parse_aggregates,
    project,
    verify_manifest,
    verify_sources,
    verify_stored,
)
from projection.backtest import RUN_LABEL_PATTERN, GraphBuilder


class LoadError(ValueError):
    """The requested aggregates file cannot be loaded."""


def _label(text: str) -> str:
    if not re.fullmatch(RUN_LABEL_PATTERN, text):
        raise argparse.ArgumentTypeError(
            f"run label {text!r} does not match {RUN_LABEL_PATTERN} (as in candidate)"
        )
    return text


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--label",
        required=True,
        type=_label,
        metavar="LABEL",
        help="the run label the folder publishes ([a-z][a-z0-9_]{1,31})",
    )
    parser.add_argument(
        "--dir",
        required=True,
        type=Path,
        metavar="DIR",
        help="the folder with aggregates_<label>.json, SHA256SUMS and <label>_<window>.db",
    )
    parser.add_argument("--write", action="store_true", help="append the graph to the store")
    parser.add_argument(
        "--check-store",
        action="store_true",
        help="read the live store, run the same gate plan, write nothing",
    )
    parser.add_argument(
        "--to-production",
        action="store_true",
        help="with --write: allow the production repository (a maintainer decision)",
    )
    args = parser.parse_args(argv)
    if args.check_store and args.write:
        parser.error("--check-store only reads; do not combine it with --write")
    if args.check_store and args.to_production:
        parser.error("--check-store never writes; drop --to-production")
    if args.to_production and not args.write:
        parser.error("--to-production only matters with --write")
    return args


def open_store(args: argparse.Namespace) -> GraphDB | None:
    """The store a ``--write`` appends to; production needs the explicit opt-in."""
    if not args.write:
        return None
    store = GraphDB.from_env()
    if store.repository == PRODUCTION_REPOSITORY and not args.to_production:
        print(
            "--write to the production repository needs --to-production: the final label is the "
            "maintainer's decision",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return store


def load_file(label: str, directory: Path) -> AggregatesFile:
    """Verify the manifest entry first, then parse the file; attach the manifest hash."""
    file_name = f"aggregates_{label}.json"
    path = directory / file_name
    if not path.is_file():
        raise LoadError(f"{path}: no aggregates file for label {label!r}")
    digest = verify_manifest(directory, file_name)
    data = parse_aggregates(path, label=label)
    return replace(data, source_file=file_name, source_sha256=digest)


def _show_verification(verification: Verification) -> bool:
    print(verification.summary())
    return verification.ok


def _show_check(check: Check) -> bool:
    print(f"{'PASS' if check.passed else 'FAIL'}  {check.name}: {check.detail}")
    return check.passed


def _show_build(data: AggregatesFile, builder: GraphBuilder) -> None:
    graph = graph_name(data.label)
    print(f"label: {data.label}")
    print(f"config: {data.config_id}")
    print(f"graph: {graph}")
    print(
        f"rows: trend_filter: {len(data.trend_filter)}; "
        f"reference_returns: {len(data.reference_returns)}"
    )
    print(f"triples: {len(builder)}")


def dry_run(data: AggregatesFile, directory: Path, started: float) -> int:
    """Manifest/parser already passed; verify the databases, build and SHACL-validate."""
    mark = time.perf_counter()
    verification = verify_sources(data, directory)
    ok = _show_verification(verification)
    print(f"timing: source verifier {time.perf_counter() - mark:.3f} s")
    mark = time.perf_counter()
    builder = project(data)
    _show_build(data, builder)
    print(f"timing: build {time.perf_counter() - mark:.3f} s")
    mark = time.perf_counter()
    try:
        parsed = gate.parse_batch(builder.turtle())
        gate.validate(parsed)
    except gate.IngestRejected as exc:
        print(f"SHACL: FAIL\n{exc}")
        return 1
    print("SHACL: conforms (gate.validate)")
    print(f"timing: SHACL {time.perf_counter() - mark:.3f} s")
    print(f"timing: total {time.perf_counter() - started:.3f} s")
    return 0 if ok else 1


def check_store(data: AggregatesFile, builder: GraphBuilder, started: float, store: GraphDB) -> int:
    """The read-only pre-flight: gate.plan with the store's context; write nothing."""
    graph = graph_name(data.label)
    mark = time.perf_counter()
    try:
        plan = gate.plan(store, builder.turtle(), graph)
    except gate.IngestRejected as exc:
        print(f"STOPPED\n{exc}", file=sys.stderr)
        return 1
    print(f"pre-flight: {plan.status.value}: {graph}")
    print(f"timing: gate plan {time.perf_counter() - mark:.3f} s")
    if plan.status is gate.IngestPlanStatus.ALREADY_IN_STORE:
        mark = time.perf_counter()
        ok = _show_check(verify_stored(store, data, builder))
        print(f"timing: stored-graph check {time.perf_counter() - mark:.3f} s")
        print(f"timing: total {time.perf_counter() - started:.3f} s")
        return 0 if ok else 1
    print(f"timing: total {time.perf_counter() - started:.3f} s")
    return 0


def write_store(
    data: AggregatesFile,
    builder: GraphBuilder,
    started: float,
    store: GraphDB,
) -> int:
    """Plan through the real gate and write the one append-only graph, then verify it."""
    graph = graph_name(data.label)
    mark = time.perf_counter()
    try:
        plan = gate.plan(store, builder.turtle(), graph)
    except gate.IngestRejected as exc:
        print(f"STOPPED\n{exc}", file=sys.stderr)
        return 1
    print(f"pre-flight: {plan.status.value}: {graph}")
    print(f"timing: gate plan {time.perf_counter() - mark:.3f} s")
    if plan.status is gate.IngestPlanStatus.ALREADY_IN_STORE:
        print(f"already-in-the-store (skipped): {graph}")
        mark = time.perf_counter()
        ok = _show_check(verify_stored(store, data, builder))
        print(f"timing: stored-graph check {time.perf_counter() - mark:.3f} s")
        print(f"timing: total {time.perf_counter() - started:.3f} s")
        return 0 if ok else 1
    mark = time.perf_counter()
    try:
        written = gate.write(store, plan)
    except gate.WriteInDoubt as exc:
        print(
            f"store error, the graph is in doubt: {exc}\n{graph} was sent but the store's answer "
            "was lost, so it may be written; do not retry blindly",
            file=sys.stderr,
        )
        return 1
    except gate.IngestRejected as exc:
        print(f"STOPPED\n{exc}", file=sys.stderr)
        return 1
    print(f"written: {graph}: {written} triples")
    print(f"timing: gate write {time.perf_counter() - mark:.3f} s")
    mark = time.perf_counter()
    ok = _show_check(verify_stored(store, data, builder))
    print(f"timing: stored-graph check {time.perf_counter() - mark:.3f} s")
    print(f"timing: total {time.perf_counter() - started:.3f} s")
    return 0 if ok else 1


def main(argv: Sequence[str] | None = None) -> int:  # noqa: PLR0911
    args = parse_args(argv)
    started = time.perf_counter()
    directory = args.dir.resolve()
    try:
        # Announce the target before any other output, without contacting the store: the manifest
        # and source checks still run before the first request. A dry run prints no banner.
        if args.check_store or args.write:
            announce_target(GraphDB.from_env())
        data = load_file(args.label, directory)
        print(f"manifest: {data.source_file} is listed; SHA-256 {data.source_sha256} matches")
        print(f"timing: manifest+parse {time.perf_counter() - started:.3f} s")
        if not args.write and not args.check_store:
            return dry_run(data, directory, started)
        mark = time.perf_counter()
        verification = verify_sources(data, directory)
        if not _show_verification(verification):
            print(
                "the source verifier failed; nothing was planned or written",
                file=sys.stderr,
            )
            return 1
        print(f"timing: source verifier {time.perf_counter() - mark:.3f} s")
        mark = time.perf_counter()
        builder = project(data)
        _show_build(data, builder)
        print(f"timing: build {time.perf_counter() - mark:.3f} s")
        if args.check_store:
            return check_store(data, builder, started, GraphDB.from_env())
        store = open_store(args)
        assert store is not None
        return write_store(data, builder, started, store)
    except (AggregatesError, LoadError) as exc:
        print(f"STOPPED\n{exc}", file=sys.stderr)
        return 1
    except sqlite3.Error as exc:
        print(f"source error: {exc} (--dir DIR)", file=sys.stderr)
        return 1
    except GraphDBError as exc:
        print(f"store error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"file error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
