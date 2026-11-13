"""The final Veto Hierarchy manifest: parse, verify and filter the delivery (Work item 46).

The manifest is the loader's only source of truth for which books, windows and configurations
belong to one delivery. It is deliberately stricter than the old delivery folder: the key is
``(label, configuration, window)``, every file is relative and hashed, and a final manifest may
not carry a ``PENDIENTE`` value. The parser never opens a database; :func:`verify_files` hashes the
files first, and only the caller opens the engine DB after that succeeds.

The closed configuration vocabulary and the graph-name helpers are here too, so the m018/meta
projectors and the ingest gate share one implementation.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: The five configurations of the final delivery.
CONFIGURATIONS: tuple[str, ...] = (
    "SYSTEM_WITH_HIERARCHY",
    "SYSTEM_WITHOUT_HIERARCHY",
    "MARKOWITZ_BASE",
    "MARKOWITZ_MV",
    "SPY",
)

#: The seven windows of the final delivery, including the independent C1 run.
WINDOWS: tuple[str, ...] = ("P1", "H1", "P3", "H2", "P2", "H3", "C1")

#: configuration -> lower-case graph/IRI slug.
CONFIGURATION_SLUGS: Mapping[str, str] = {
    "SYSTEM_WITH_HIERARCHY": "system_with_hierarchy",
    "SYSTEM_WITHOUT_HIERARCHY": "system_without_hierarchy",
    "MARKOWITZ_BASE": "markowitz_base",
    "MARKOWITZ_MV": "markowitz_mv",
    "SPY": "spy",
}

#: configuration -> TBox individual.
CONFIGURATION_IRIS: Mapping[str, str] = {
    "SYSTEM_WITH_HIERARCHY": "Configuration_SystemWithHierarchy",
    "SYSTEM_WITHOUT_HIERARCHY": "Configuration_SystemWithoutHierarchy",
    "MARKOWITZ_BASE": "Configuration_MarkowitzBase",
    "MARKOWITZ_MV": "Configuration_MarkowitzMV",
    "SPY": "Configuration_SPY",
}

LABEL_PATTERN = r"[a-z][a-z0-9_]{1,31}"
_WINDOW_PATTERN = re.compile(r"(?:[PH][0-9]+|C[0-9]+)")
_LABEL = re.compile(LABEL_PATTERN)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SLUG = re.compile(r"[a-z][a-z0-9_]{1,31}")
_PENDING = "PENDIENTE"
_TOP_LEVEL = frozenset(
    {
        "manifest_version",
        "status",
        "label",
        "created_at",
        "key",
        "key_note",
        "windows",
        "price_mask",
        "prereg",
        "configurations",
        "control_counts",
    }
)
_CONFIGURATION_KEYS = frozenset(
    {
        "configuration",
        "name_es",
        "name_en",
        "source_kind",
        "selected_variant",
        "runs",
        "note",
        "book_code_note",
        "example_note",
    }
)
_RUN_KEYS = frozenset(
    {
        "window",
        "db_file",
        "db_sha256",
        "run_id",
        "book_code",
        "book_id",
        "jsonl_file",
        "jsonl_sha256",
        "jsonl_note",
        "rankings_file",
        "rankings_sha256",
        "panels_file",
        "panels_sha256",
        "scales_file",
        "scales_sha256",
        "manager_calls_file",
        "manager_calls_sha256",
        "narrator_file",
        "narrator_sha256",
        "news_actions_file",
        "news_actions_sha256",
        "code_version",
        "files_sha256",
        "daily_file",
        "daily_sha256",
        "weights_file",
        "weights_sha256",
        "aggregates_file",
        "aggregates_sha256",
        "window_filter",
    }
)
_HASHED_FILE_KEYS = (
    ("price_mask", "file", "sha256"),
    ("runs", "db_file", "db_sha256"),
    ("runs", "jsonl_file", "jsonl_sha256"),
    ("runs", "rankings_file", "rankings_sha256"),
    ("runs", "panels_file", "panels_sha256"),
    ("runs", "scales_file", "scales_sha256"),
    ("runs", "manager_calls_file", "manager_calls_sha256"),
    ("runs", "narrator_file", "narrator_sha256"),
    ("runs", "news_actions_file", "news_actions_sha256"),
    ("runs", "daily_file", "daily_sha256"),
    ("runs", "weights_file", "weights_sha256"),
    ("runs", "aggregates_file", "aggregates_sha256"),
)


class VetoManifestError(ValueError):
    """The final manifest, its hashes or its runs cannot be accepted."""


def configuration_slug(value: str) -> str:
    """The closed configuration -> slug mapping; an unknown string is an error."""
    try:
        return CONFIGURATION_SLUGS[value]
    except KeyError:
        raise VetoManifestError(
            f"configuration {value!r} is not one of {', '.join(CONFIGURATIONS)}"
        ) from None


def configuration_iri(value: str) -> str:
    """The local name of the TBox individual for one configuration."""
    try:
        return CONFIGURATION_IRIS[value]
    except KeyError:
        raise VetoManifestError(
            f"configuration {value!r} is not one of {', '.join(CONFIGURATIONS)}"
        ) from None


def backtest_graph_name(label: str, window: str, configuration: str) -> str:
    """One configuration/window m018 graph."""
    return f"urn:graph:derived:backtest:{_key(label, window, configuration)}"


def selection_graph_name(label: str, window: str, configuration: str) -> str:
    """One configuration/window selection graph."""
    return f"urn:graph:derived:backtest:selection:{_key(label, window, configuration)}"


def meta_graph_name(label: str) -> str:
    """The one metadata graph of a label (it holds every configuration/window run)."""
    _check_label(label)
    return f"urn:graph:derived:backtest:meta:{label}"


def aggregates_graph_name(label: str, configuration: str) -> str:
    """The per-configuration aggregates graph."""
    _check_label(label)
    return f"urn:graph:derived:backtest:aggregates:{label}:{configuration_slug(configuration)}"


def external_graph_name(label: str) -> str:
    """The unchanged external MARKOWITZ_MV graph."""
    _check_label(label)
    return f"urn:graph:derived:backtest:external:{label}"


def entity_stem(label: str, window: str, configuration: str) -> str:
    """The label/window/slug stem shared by every IRI of one configuration/window."""
    return f"{_key(label, window, configuration).replace(':', '_')}"


def _key(label: str, window: str, configuration: str) -> str:
    _check_label(label)
    if not _WINDOW_PATTERN.fullmatch(window):
        raise VetoManifestError(f"window {window!r} does not match P<n>, H<n> or C<n>")
    return f"{label}:{window}:{configuration_slug(configuration)}"


def _check_label(label: str) -> None:
    if not _LABEL.fullmatch(label):
        raise VetoManifestError(f"label {label!r} does not match {LABEL_PATTERN}")


@dataclass(frozen=True)
class ManifestRun:
    """One run of one configuration: its engine DB and the optional detail files."""

    configuration: str
    window: str
    db_file: Path
    db_sha256: str
    run_id: int
    book_code: str
    book_id: int
    source_kind: str
    files: Mapping[str, Path] = field(default_factory=dict)
    file_hashes: Mapping[Path, str] = field(default_factory=dict)
    extra_hashes: Mapping[Path, str] = field(default_factory=dict)
    code_version: str | None = None

    @property
    def slug(self) -> str:
        return configuration_slug(self.configuration)

    @property
    def key(self) -> tuple[str, str]:
        return (self.configuration, self.window)


@dataclass(frozen=True)
class PriceMask:
    """The mask file and its declared SHA-256."""

    path: Path
    sha256: str
    rule: str


@dataclass(frozen=True)
class VetoManifest:
    """A parsed manifest, before or after its files have been hashed."""

    path: Path
    root: Path
    status: str | None
    label: str
    created_at: str
    windows: tuple[str, ...]
    price_mask: PriceMask
    prereg: Mapping[str, str]
    configurations: tuple[Mapping[str, Any], ...]
    runs: tuple[ManifestRun, ...]
    control_counts: object

    @property
    def draft(self) -> bool:
        return bool(self.status and self.status.upper().startswith("BORRADOR"))

    @property
    def engine_runs(self) -> tuple[ManifestRun, ...]:
        """The runs the m018/meta loader reads: the three engine-DB configurations."""
        return tuple(run for run in self.runs if run.source_kind == "engine_db")


# --- parsing ------------------------------------------------------------------------------------


def read_manifest(path: str | Path) -> VetoManifest:  # noqa: C901 -- one branch per manifest failure
    """Parse ``manifest_final.json`` strictly; no file is opened or hashed."""
    manifest_path = Path(path)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise VetoManifestError(f"{manifest_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise VetoManifestError(f"{manifest_path}: invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise VetoManifestError(f"{manifest_path}: the manifest must be a JSON object")
    unknown = sorted(set(raw) - _TOP_LEVEL)
    if unknown:
        raise VetoManifestError(f"{manifest_path}: unknown top-level key(s): {', '.join(unknown)}")
    status = _optional_str(raw.get("status"), "status")
    draft = bool(status and status.upper().startswith("BORRADOR"))
    _required_str(raw, "manifest_version")
    label = _required_str(raw, "label")
    _check_label(label)
    created_at = _required_str(raw, "created_at")
    _date(created_at, "created_at")
    key = raw.get("key")
    if key != ["label", "configuration", "window"]:
        raise VetoManifestError(
            f'{manifest_path}: key must be ["label", "configuration", "window"], got {key!r}'
        )
    windows = _windows(raw.get("windows"))
    root = manifest_path.resolve().parent
    price_mask = _price_mask(raw.get("price_mask"), root, draft)
    prereg = _prereg(raw.get("prereg"), draft)
    configurations = raw.get("configurations")
    if not isinstance(configurations, list):
        raise VetoManifestError(f"{manifest_path}: configurations must be a list")
    names = [_configuration_name(item, index) for index, item in enumerate(configurations)]
    if len(set(names)) != len(names):
        raise VetoManifestError(f"{manifest_path}: a configuration is listed twice")
    if set(names) != set(CONFIGURATIONS):
        missing = sorted(set(CONFIGURATIONS) - set(names))
        extra = sorted(set(names) - set(CONFIGURATIONS))
        raise VetoManifestError(
            f"{manifest_path}: configurations must be the five closed names; "
            f"missing {missing}, unknown {extra}"
        )
    runs: list[ManifestRun] = []
    for item in configurations:
        runs.extend(_configuration_runs(item, root, draft))
    keys = [run.key for run in runs]
    if len(set(keys)) != len(keys):
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        raise VetoManifestError(
            f"{manifest_path}: duplicate (configuration, window) key(s): {duplicates}"
        )
    return VetoManifest(
        path=manifest_path,
        root=root,
        status=status,
        label=label,
        created_at=created_at,
        windows=windows,
        price_mask=price_mask,
        prereg=prereg,
        configurations=tuple(configurations),
        runs=tuple(runs),
        control_counts=raw.get("control_counts"),
    )


def _required_str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise VetoManifestError(f"{key} must be a non-empty string")
    return value


def _optional_str(value: object, where: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise VetoManifestError(f"{where} must be a string when present")
    return value


def _date(value: str, where: str) -> None:
    if not _DATE.fullmatch(value):
        raise VetoManifestError(f"{where} {value!r} is not a YYYY-MM-DD date")
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        raise VetoManifestError(f"{where} {value!r} is not a real date") from None


def _windows(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise VetoManifestError("windows must be a non-empty list")
    windows = [str(window) for window in value]
    unknown = [window for window in windows if not _WINDOW_PATTERN.fullmatch(window)]
    if unknown:
        raise VetoManifestError(f"unknown window id(s): {', '.join(unknown)}")
    if len(set(windows)) != len(windows):
        raise VetoManifestError("windows lists an id twice")
    if set(windows) != set(WINDOWS):
        missing = sorted(set(WINDOWS) - set(windows))
        extra = sorted(set(windows) - set(WINDOWS))
        raise VetoManifestError(
            f"windows must be the seven final windows; missing {missing}, unknown {extra}"
        )
    return tuple(windows)


def _price_mask(value: object, root: Path, draft: bool) -> PriceMask:
    if not isinstance(value, dict):
        raise VetoManifestError("price_mask must be an object")
    unknown = sorted(set(value) - {"file", "sha256", "rule"})
    if unknown:
        raise VetoManifestError(f"price_mask: unknown key(s): {', '.join(unknown)}")
    file_name = _required_str(value, "file")
    digest = _required_str(value, "sha256")
    _hash(digest, "price_mask.sha256", draft)
    rule = _required_str(value, "rule")
    path = _safe_path(Path(file_name), root, "price_mask.file")
    return PriceMask(path, digest, rule)


def _prereg(value: object, draft: bool) -> Mapping[str, str]:
    if not isinstance(value, dict) or not value:
        raise VetoManifestError("prereg must be a non-empty object")
    out: dict[str, str] = {}
    for name, digest in value.items():
        if not isinstance(name, str) or not name:
            raise VetoManifestError("prereg has an empty file name")
        if not isinstance(digest, str) or not digest:
            raise VetoManifestError(f"prereg.{name} must be a string")
        _hash(digest, f"prereg.{name}", draft)
        out[name] = digest
    return out


def _configuration_name(item: object, index: int) -> str:
    if not isinstance(item, dict):
        raise VetoManifestError(f"configurations[{index}] must be an object")
    unknown = sorted(set(item) - _CONFIGURATION_KEYS)
    if unknown:
        raise VetoManifestError(f"configurations[{index}]: unknown key(s): {', '.join(unknown)}")
    name = _required_str(item, "configuration")
    configuration_slug(name)
    return name


def _configuration_runs(item: Mapping[str, Any], root: Path, draft: bool) -> list[ManifestRun]:
    name = str(item["configuration"])
    source_kind = _required_str(item, "source_kind")
    if source_kind not in ("engine_db", "series_csv"):
        raise VetoManifestError(
            f"{name}: source_kind must be engine_db or series_csv, got {source_kind!r}"
        )
    runs = item.get("runs")
    if not isinstance(runs, list) or not runs:
        raise VetoManifestError(f"{name}: runs must be a non-empty list")
    return [_run(name, source_kind, run, root, index, draft) for index, run in enumerate(runs)]


def _run(  # noqa: PLR0913, PLR0917 -- the fields are the manifest row
    configuration: str,
    source_kind: str,
    raw: object,
    root: Path,
    index: int,
    draft: bool,
) -> ManifestRun:
    where = f"{configuration}.runs[{index}]"
    if not isinstance(raw, dict):
        raise VetoManifestError(f"{where} must be an object")
    unknown = sorted(set(raw) - _RUN_KEYS)
    if unknown:
        raise VetoManifestError(f"{where}: unknown key(s): {', '.join(unknown)}")
    window = _required_str(raw, "window")
    if not _WINDOW_PATTERN.fullmatch(window):
        raise VetoManifestError(f"{where}: window {window!r} does not match P<n>, H<n> or C<n>")
    if source_kind == "series_csv":
        if "db_file" in raw:
            raise VetoManifestError(f"{where}: a series run has no db_file")
        files, hashes = _run_files(raw, root, where, draft)
        extra = _files_sha256(raw, root, where, draft)
        return ManifestRun(
            configuration,
            window,
            Path(),
            "",
            0,
            "",
            0,
            source_kind,
            files=files,
            file_hashes=hashes,
            extra_hashes=extra,
        )
    db_file = _run_file(raw, "db_file", root, where)
    digest = _required_str(raw, "db_sha256")
    _hash(digest, f"{where}.db_sha256", draft)
    run_id = _positive_int(raw.get("run_id"), f"{where}.run_id", draft)
    book_code = _required_str(raw, "book_code")
    book_id = _positive_int(raw.get("book_id"), f"{where}.book_id", draft)
    files, hashes = _run_files(raw, root, where, draft)
    extra = _files_sha256(raw, root, where, draft)
    return ManifestRun(
        configuration=configuration,
        window=window,
        db_file=db_file,
        db_sha256=digest,
        run_id=run_id,
        book_code=book_code,
        book_id=book_id,
        source_kind=source_kind,
        files=files,
        file_hashes=hashes,
        extra_hashes=extra,
        code_version=_optional_str(raw.get("code_version"), f"{where}.code_version"),
    )


def _run_files(
    raw: Mapping[str, Any], root: Path, where: str, draft: bool
) -> tuple[dict[str, Path], dict[Path, str]]:
    files: dict[str, Path] = {}
    hashes: dict[Path, str] = {}
    for _, file_key, hash_key in _HASHED_FILE_KEYS:
        if file_key not in raw or raw[file_key] is None:
            continue
        file_name = raw[file_key]
        if not isinstance(file_name, str) or not file_name:
            raise VetoManifestError(f"{where}.{file_key} must be a non-empty string")
        path = _run_file(raw, file_key, root, where)
        files[file_key] = path
        if hash_key in raw and raw[hash_key] is not None:
            declared = str(raw[hash_key])
            _hash(declared, f"{where}.{hash_key}", draft)
            hashes[path] = declared
        elif not draft:
            raise VetoManifestError(f"{where}.{file_key}: a final manifest needs {hash_key}")
    return files, hashes


def _files_sha256(raw: Mapping[str, Any], root: Path, where: str, draft: bool) -> dict[Path, str]:
    value = raw.get("files_sha256")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise VetoManifestError(f"{where}.files_sha256 must be an object")
    hashes: dict[Path, str] = {}
    for name, declared in value.items():
        if not isinstance(name, str) or not name:
            raise VetoManifestError(f"{where}.files_sha256 has an empty file name")
        if not isinstance(declared, str):
            raise VetoManifestError(f"{where}.files_sha256.{name} must be a string")
        _hash(declared, f"{where}.files_sha256.{name}", draft)
        hashes[_safe_path(Path(name), root, f"{where}.files_sha256.{name}")] = declared
    return hashes


def _run_file(raw: Mapping[str, Any], key: str, root: Path, where: str) -> Path:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise VetoManifestError(f"{where}.{key} must be a non-empty string")
    return _safe_path(Path(value), root, f"{where}.{key}")


def _safe_path(path: Path, root: Path, where: str) -> Path:
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise VetoManifestError(f"{where}: {str(path)!r} must be a relative path without '..'")
    if not path.parts:
        raise VetoManifestError(f"{where}: empty path")
    resolved = (root / path).resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise VetoManifestError(f"{where}: {str(path)!r} escapes the delivery root")
    return resolved


def _hash(value: str, where: str, draft: bool) -> None:
    if _PENDING in value.upper():
        if draft:
            return
        raise VetoManifestError(f"{where}: a final manifest may not contain PENDIENTE")
    if not _SHA256.fullmatch(value):
        raise VetoManifestError(f"{where}: {value!r} is not a lowercase SHA-256")


def _positive_int(value: object, where: str, draft: bool = False) -> int:
    if isinstance(value, str) and draft and _PENDING in value.upper():
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise VetoManifestError(f"{where}: {value!r} is not a positive integer")
    return value


# --- hashing ------------------------------------------------------------------------------------


def hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Stream one file through SHA-256."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
    except OSError as exc:
        raise VetoManifestError(f"{path}: {exc}") from exc
    return digest.hexdigest()


def verify_files(
    manifest: VetoManifest,
    *,
    hasher: Callable[[Path], str] = hash_file,
) -> dict[Path, str]:
    """Hash the mask and every named file; compare declared hashes.

    The caller must not open an engine DB until this succeeds. The mask is verified first, then
    the runs in manifest order.
    """
    verified: dict[Path, str] = {}
    _verify_one(manifest.price_mask.path, manifest.price_mask.sha256, verified, hasher)
    for run in manifest.runs:
        if run.source_kind == "engine_db":
            _verify_one(run.db_file, run.db_sha256, verified, hasher)
        for path in run.files.values():
            declared = run.file_hashes.get(path, "")
            if declared:
                _verify_one(path, declared, verified, hasher)
        for path, declared in run.extra_hashes.items():
            _verify_one(path, declared, verified, hasher)
    return verified


def _verify_one(
    path: Path,
    declared: str,
    verified: dict[Path, str],
    hasher: Callable[[Path], str],
) -> None:
    if not path.is_file():
        raise VetoManifestError(f"missing file: {path}")
    actual = hasher(path).lower()
    if _PENDING not in declared.upper() and actual != declared.lower():
        raise VetoManifestError(f"{path}: SHA-256 mismatch: manifest {declared}, actual {actual}")
    verified[path] = actual


# --- filters ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FilterReport:
    """What the manifest filters removed and why."""

    configuration: str
    window: str
    book_code: str
    book_id: int
    removed: Mapping[str, int] = field(default_factory=dict)
    reasons: Mapping[str, int] = field(default_factory=dict)


def filter_rows(
    rows: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    configuration: str,
    window: str,
    book_code: str,
    book_id: int,
) -> tuple[dict[str, list[Mapping[str, Any]]], FilterReport]:
    """Keep only the manifest's book, its loaded actions/alerts and its four tests.

    The rule is the same for every configuration: the finish DB is not trusted to name its own
    configuration, and ``:armCode`` is never used to infer it. The manifest's ``book_code`` and
    ``book_id`` select the one book. A twin book, its alerts/actions and the tests that do not
    compare the configured System against ``MARKOWITZ_BASE`` are removed.
    """
    configuration_slug(configuration)
    if not _WINDOW_PATTERN.fullmatch(window):
        raise VetoManifestError(f"window {window!r} does not match P<n>, H<n> or C<n>")
    removed: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    books = [
        row
        for row in rows.get("v_book", ())
        if int(row.get("book_id", -1)) == book_id
        and str(row.get("arm_code")) == book_code
        and str(row.get("window_id")) == window
    ]
    if len(books) != 1:
        raise VetoManifestError(
            f"{configuration}/{window}: expected one v_book row for book_id {book_id} "
            f"({book_code}), found {len(books)}"
        )
    out: dict[str, list[Mapping[str, Any]]] = {"v_book": books}
    removed["v_book"] = len(rows.get("v_book", ())) - len(books)
    reasons["twin or other book"] += removed["v_book"]
    actions = [
        row
        for row in rows.get("v_guard_action", ())
        if int(row.get("book_id", -1)) == book_id
        and str(row.get("window_id", window)) == window
        and str(row.get("status")) != "ARM_DISABLED"
    ]
    removed["v_guard_action"] = len(rows.get("v_guard_action", ())) - len(actions)
    reasons["twin book or ARM_DISABLED"] = removed["v_guard_action"]
    alert_ids = {int(row["alert_id"]) for row in actions if row.get("alert_id") is not None}
    alerts = [
        row
        for row in rows.get("v_guard_alert", ())
        if str(row.get("window_id")) == window and int(row.get("alert_id", -1)) in alert_ids
    ]
    removed["v_guard_alert"] = len(rows.get("v_guard_alert", ())) - len(alerts)
    reasons["alert without a loaded action"] = removed["v_guard_alert"]
    out["v_guard_action"] = actions
    out["v_guard_alert"] = alerts
    for view in ("v_book_rebalance", "v_book_weight_daily", "v_book_daily_performance"):
        kept = [row for row in rows.get(view, ()) if int(row.get("book_id", -1)) == book_id]
        removed[view] = len(rows.get(view, ())) - len(kept)
        reasons["twin book"] += removed[view]
        out[view] = kept
    summaries = [
        row
        for row in rows.get("v_portfolio_period_summary", ())
        if int(row.get("book_id", -1)) == book_id
    ]
    removed["v_portfolio_period_summary"] = len(rows.get("v_portfolio_period_summary", ())) - len(
        summaries
    )
    reasons["twin book"] += removed["v_portfolio_period_summary"]
    out["v_portfolio_period_summary"] = summaries
    tests = [
        row
        for row in rows.get("v_backtest_test", ())
        if str(row.get("window_id")) == window
        and {str(row.get("arm_a")), str(row.get("arm_b"))} == {book_code, "MARKOWITZ_BASE"}
    ]
    removed["v_backtest_test"] = len(rows.get("v_backtest_test", ())) - len(tests)
    reasons["test not System-vs-Markowitz"] = removed["v_backtest_test"]
    out["v_backtest_test"] = tests
    return out, FilterReport(
        configuration, window, book_code, book_id, dict(removed), dict(reasons)
    )
