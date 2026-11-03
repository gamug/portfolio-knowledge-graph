"""Load the asset master (``:Universe``, ``:Asset``, ``:UniverseMembership``) into the store.

``portfolio-data-mining``'s point-in-time ``universe.db`` is the asset master (D1, T-100):
:mod:`etl.asset_master` already turns it into one ``:Asset`` per symbol and one
``:UniverseMembership`` per stint in the single ``:SP500Index`` ``:Universe``. That module writes
flat Turtle for ``cli/build_data_ttl.py``; this one puts the same individuals into a GraphDB named
graph **through the ingest gate**, so a backtest or a score batch that links ``:Asset`` nodes finds
them in the store instead of being refused (T-220).

    uv run python cli/load_universe.py                  # dry run: read, build, SHACL-validate
    uv run python cli/load_universe.py --write          # append through the gate

**The graph is the quarter graph, not ``urn:graph:reference``.** ``docs/07`` assigns the universe
ABox to ``urn:graph:universe:{year}-Q{n}``, computed here from ``--as-of`` (the day the run sees the
catalog). ``urn:graph:reference`` holds ``schema/reference.ttl``, which ``cli/load_schema.py``
drops and rewrites as a whole on every schema reload: ABox individuals written there would vanish
on the next reload, and the loader could not append to it. The quarter graph is append-only and
gate-accepted, and the catalog is the membership boundary of that quarter. ``reference.ttl`` keeps
its five worked-example assets: the loader reads their tickers and emits only their memberships,
so those ``:Asset`` individuals are neither re-declared nor changed (a second declaration would
clash with ``cikNumber``'s functional-property contract, as in the ETL).

``--since`` keeps the stints that were still open on or after that date (``valid_to`` absent, or
``valid_to >= since``); the default ``2019-01-02`` drops a ticker's earlier company when upstream
reused the symbol (``CEG``, ``DELL``, ``Q``), so the one ``:Asset`` per symbol describes the
company the backtest windows and the live index contain. The dropped stints are counted, never
silently omitted.

A dry run (the default) contacts no store: it reads ``universe.db``, builds the batch and runs the
gate's store-free checks plus ``shapes.ttl`` with the local ``schema/reference.ttl`` standing in
for what a loaded store would hold about the industries and the five worked-example assets.
``--write`` appends the batch through :func:`kg_store.gate.ingest`, which re-validates it against
the store's own copy of those individuals, and writing the production repository
(``KG_REPOSITORY=portfolio``) also needs ``--to-production``, as ``cli/project_backtest.py`` does.

The load is append-only, as ``docs/07`` requires. Once a quarter's graph exists the gate refuses a
second load; a load into a later quarter re-declares the same ``:Asset``/``:Universe`` individuals
and the gate's check 6 refuses those, so this is a one-time catalog load per repository (a new
automation gets its own repository, Work item 17). A later quarter's *changed* memberships are a
different batch: only their new individuals, not the catalog again.
"""

from __future__ import annotations

import argparse
import datetime
import io
import sqlite3
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import rdflib

from etl import asset_master, config
from etl.build_data_ttl import reference_asset_tickers
from kg_store import gate
from kg_store.graphdb import PRODUCTION_REPOSITORY, GraphDB, GraphDBError, schema_dir

#: Stints closed before this date are dropped by default: a ticker reused by another company
#: (``CEG``, ``DELL``, ``Q``) keeps only the era the backtests and the live index can see.
DEFAULT_SINCE = "2019-01-02"

_PREFIXES = (
    "@prefix :      <https://thesis.local/kg/portfolio#> .\n"
    "@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .\n"
    "@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .\n\n"
)


@dataclass(frozen=True)
class UniverseBatch:
    """One quarter's asset-master batch and the numbers the run reports."""

    graph: str
    as_of: str
    since: str
    data: bytes
    triples: int
    summary: asset_master.UniverseSummary
    warnings: tuple[str, ...]
    kept: tuple[asset_master.Stint, ...]
    dropped: tuple[asset_master.Stint, ...]
    already_defined: frozenset[str]
    cik_less_open: tuple[str, ...]


def today() -> str:
    """Today in UTC: the default ``--as-of``."""
    return datetime.datetime.now(datetime.UTC).date().isoformat()


def iso_date(text: str) -> str:
    """``--since``/``--as-of``: a ``YYYY-MM-DD`` date, refused here rather than at the gate."""
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a YYYY-MM-DD date") from None


def quarter(as_of: str) -> str:
    """The calendar quarter of an ISO date, ``YYYY-Qn`` (the gate's accepted universe name)."""
    day = datetime.date.fromisoformat(as_of)
    return f"{day.year}-Q{(day.month - 1) // 3 + 1}"


def graph_name(as_of: str) -> str:
    """The append-only universe graph for ``--as-of`` (``docs/07``)."""
    return f"urn:graph:universe:{quarter(as_of)}"


def keep_stints(stints: Sequence[asset_master.Stint], since: str) -> list[asset_master.Stint]:
    """The stints still open on or after ``since`` (``validTo`` is exclusive)."""
    return [s for s in stints if s.valid_to is None or s.valid_to >= since]


def cik_less_open(stints: Sequence[asset_master.Stint]) -> list[str]:
    """Symbols whose loaded ``:Asset`` has no CIK but keeps an open membership.

    ``build_assets`` describes an ``:Asset`` with its latest stint, so a missing CIK there and an
    open stint anywhere is exactly what ``AssetShape``'s CIK-or-closed rule refuses.
    """
    by_symbol: dict[str, list[asset_master.Stint]] = {}
    for stint in stints:
        by_symbol.setdefault(stint.symbol, []).append(stint)
    return sorted(
        symbol
        for symbol, symbol_stints in by_symbol.items()
        if any(s.valid_to is None for s in symbol_stints)
        and not max(symbol_stints, key=lambda s: s.valid_from).cik
    )


def render(
    stints: list[asset_master.Stint],
    already_defined: set[str],
    since: str,
    as_of: str,
    warnings: list[str],
) -> tuple[bytes, asset_master.UniverseSummary]:
    """Build the Turtle batch for ``stints``; no store and no validation."""
    out = io.StringIO()
    out.write(_PREFIXES)
    out.write(
        f"# Asset master for {quarter(as_of)} (as of {as_of}), generated by "
        f"cli/load_universe.py from universe.db.\n"
        f"# Stints kept: valid_to absent or >= {since}.\n\n"
    )
    summary = asset_master.build_assets(stints, out, warnings, already_defined)
    return out.getvalue().encode("utf-8"), summary


def plan(
    db_path: str | Path, since: str = DEFAULT_SINCE, as_of: str | None = None
) -> UniverseBatch:
    """Read ``universe.db`` and build the batch for the quarter graph of ``as_of``."""
    as_of = as_of or today()
    path = Path(db_path)
    warnings: list[str] = []
    stints = asset_master.read_stints(path, warnings)
    kept = keep_stints(stints, since)
    dropped = [s for s in stints if s not in kept]
    already_defined = reference_asset_tickers()
    data, summary = render(kept, already_defined, since, as_of, warnings)
    summary = replace(summary, file_mtime=path.stat().st_mtime)
    return UniverseBatch(
        graph=graph_name(as_of),
        as_of=as_of,
        since=since,
        data=data,
        triples=len(gate.parse_batch(data)),
        summary=summary,
        warnings=tuple(warnings),
        kept=tuple(kept),
        dropped=tuple(dropped),
        already_defined=frozenset(already_defined),
        cik_less_open=tuple(cik_less_open(kept)),
    )


def reference_context(refs: set[rdflib.URIRef], directory: Path) -> rdflib.Graph:
    """What ``schema/reference.ttl`` says about the individuals a dry-run batch points at.

    A loaded store holds the same triples in ``urn:graph:reference``; only their subjects are
    needed, since a reference is read for its type and the shape paths on it.
    """
    reference = rdflib.Graph().parse(directory / "reference.ttl", format="turtle")
    context = rdflib.Graph()
    for subject, predicate, obj in reference:
        if subject in refs:
            context.add((subject, predicate, obj))
    return context


def check(batch: UniverseBatch, directory: Path | None = None) -> None:
    """Dry-run validation: the gate's checks and ``shapes.ttl``, no store.

    Raises :class:`kg_store.gate.IngestRejected` (or ``ShaclRejected``) when the batch is refused.
    """
    directory = (directory or schema_dir()).resolve()
    data = gate.parse_batch(batch.data)
    schema = gate.load_gate_schema(directory)
    refs = gate.references(data, schema)
    gate.validate(data, directory, reference_context(refs, directory))


def write(batch: UniverseBatch, store: GraphDB, directory: Path | None = None) -> int:
    """Append the batch through the gate; returns the triples written."""
    return gate.ingest(store, batch.data, batch.graph, directory)


def _symbols(stints: Sequence[asset_master.Stint]) -> set[str]:
    return {s.symbol for s in stints}


def report(batch: UniverseBatch, db_path: Path) -> list[str]:
    """The end-of-run summary: what ``--since`` kept and dropped, and what was built."""
    all_stints = [*batch.kept, *batch.dropped]
    kept_symbols, dropped_symbols = _symbols(batch.kept), _symbols(batch.dropped)
    gone, later = dropped_symbols - kept_symbols, dropped_symbols & kept_symbols
    reused = len(batch.already_defined & kept_symbols)
    lines = [
        f"universe.db: {db_path}",
        f"  {batch.summary.freshness_line()}",
        f"--since {batch.since} (as of {batch.as_of}): kept {len(batch.kept)} of "
        f"{len(all_stints)} stint(s) over {len(kept_symbols)} symbol(s); dropped "
        f"{len(batch.dropped)} stint(s) over {len(dropped_symbols)} symbol(s) "
        f"({len(gone)} symbol(s) not loaded at all, {len(later)} with a later stint kept)",
        f"Assets: {batch.summary.assets_written} written"
        + (f", {reused} already in reference.ttl" if reused else "")
        + f" ({len(batch.summary.tickers)} symbol(s) loaded)",
        f"Memberships: {batch.summary.memberships} "
        f"({batch.summary.open_memberships} open, {batch.summary.closed_memberships} closed)",
        f"target graph: {batch.graph}",
        f"triples: {batch.triples}",
    ]
    if batch.cik_less_open:
        lines.append(
            f"CIK-less with an open membership ({len(batch.cik_less_open)}): "
            + ", ".join(batch.cik_less_open)
            + " -- AssetShape refuses these"
        )
    return lines


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--since",
        type=iso_date,
        default=DEFAULT_SINCE,
        metavar="YYYY-MM-DD",
        help=f"keep stints open on or after this date (default: {DEFAULT_SINCE})",
    )
    parser.add_argument(
        "--as-of",
        type=iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="the day the catalog is seen as of; names the quarter graph (default: today in UTC)",
    )
    parser.add_argument("--write", action="store_true", help="append the batch to the store")
    parser.add_argument(
        "--to-production",
        action="store_true",
        help="with --write: allow the production repository (a maintainer decision)",
    )
    args = parser.parse_args(argv)
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
            "--write to the production repository needs --to-production: the asset master is a "
            "catalog every later graph links to, so loading it is the maintainer's decision",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return store


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    db_path = config.universe_db_path()
    started = time.time()
    try:
        store = open_store(args)
        batch = plan(db_path, args.since, args.as_of)
        for line in report(batch, db_path):
            print(line)
        if batch.warnings:
            print(f"{len(batch.warnings)} warning(s):")
            for warning in batch.warnings:
                print(f"  - {warning}")
        if store is None:
            check(batch)
            print("SHACL: conforms (gate.validate; dry run, nothing written)")
        else:
            written = write(batch, store)
            print(f"written: {written} triples to {batch.graph}")
    except gate.IngestRejected as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 1
    except sqlite3.Error as exc:  # a missing database, or one without universe_membership
        print(f"source error: {exc} (SQL_UNIVERSE_DB)", file=sys.stderr)
        return 1
    except GraphDBError as exc:
        print(f"store error: {exc}", file=sys.stderr)
        return 1
    except (OSError, SyntaxError) as exc:
        print(f"file error: {exc}", file=sys.stderr)
        return 1
    print(f"done in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
