"""Read one final-backtest delivery folder: its windows, manifest and configuration (Work item 35).

A delivery is a folder of ``<label>_<window>.db`` files, a ``SHA256SUMS`` manifest in sha256sum
format and a ``config_<label>.md`` whose YAML front matter names the code commit, the pull request
and the results document. The loader reads all three before it contacts a store:

* the window vocabulary is the final backtest's six windows (``P1``, ``H1``, ``P3``, ``H2``,
  ``P2``, ``H3``); any subset is valid, but an unknown window is an input error;
* the manifest is verified by streaming each database in 1 MiB chunks, before any database is
  opened for its rows; a present manifest is never ignored;
* the configuration body is kept byte for byte (hard line breaks included) for
  ``:RunConfiguration``'s ``rdfs:comment``, and every front-matter scalar stays a string, so
  ``pr: 192`` and ``code_commit: 537e864`` keep their spelling.

The processed order is chronological by each database's ``v_book.d_start``/``d_end``, never by
window name: ``P3`` precedes ``P2``. The pilot folder has neither delivery file; the explicit
``--no-manifest --no-config`` pair is the legacy mode and disables the metadata graph.
"""

from __future__ import annotations

import datetime
import hashlib
import re
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from projection.backtest import read_view
from projection.source import FinancialSource

#: The final backtest's windows. Membership is fixed; processing order is read from each database,
#: never from this tuple or from the file names.
FINAL_WINDOWS: tuple[str, ...] = ("P1", "H1", "P3", "H2", "P2", "H3")
ALLOWED_WINDOW_SET = frozenset(FINAL_WINDOWS)

MANIFEST_NAME = "SHA256SUMS"
CHUNK_SIZE = 1024 * 1024

_HASH_LINE = re.compile(r"(?P<hash>[0-9a-fA-F]{64})  (?P<name>.+)")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_REQUIRED_KEYS = ("label", "code_commit", "pr", "results_doc")
_OPTIONAL_KEYS = ("config_id", "status")


class DeliveryError(ValueError):
    """A delivery folder, manifest, database window or configuration is not usable."""


class ManifestError(DeliveryError):
    """The manifest is missing, malformed or does not match a database."""


class ConfigError(DeliveryError):
    """The configuration file is missing, malformed or names another label."""


@dataclass(frozen=True)
class WindowFile:
    """One ``<label>_<window>.db`` discovered in a delivery folder."""

    path: Path
    window: str
    label: str


@dataclass(frozen=True)
class Manifest:
    """A parsed ``SHA256SUMS``: its path and name -> lowercase hash entries."""

    path: Path
    entries: Mapping[str, str]


@dataclass(frozen=True)
class RunConfig:
    """The frozen ``config_<label>.md`` front matter and body."""

    path: Path
    label: str
    code_commit: str
    pr: str
    results_doc: str
    body: str
    config_id: str | None = None
    status: str | None = None
    warnings: tuple[str, ...] = ()


#: The name the rest of the projection uses for :class:`RunConfig`.
RunConfiguration = RunConfig


def manifest_path(directory: Path) -> Path | None:
    """The folder's ``SHA256SUMS`` when it exists; None otherwise."""
    path = directory / MANIFEST_NAME
    return path if path.is_file() else None


def config_path(directory: Path, label: str) -> Path:
    """The folder's ``config_<label>.md`` path (it may not exist)."""
    return directory / f"config_{label}.md"


def window_sequence(value: str) -> tuple[str, ...]:
    """Split one ``--windows`` value (``P1,H1``) into validated window ids, order preserved."""
    windows: list[str] = []
    for raw in value.split(","):
        window = raw.strip()
        if not window:
            raise DeliveryError("--windows contains an empty window id")
        if window not in ALLOWED_WINDOW_SET:
            raise DeliveryError(f"window {window!r} is not one of {', '.join(FINAL_WINDOWS)}")
        windows.append(window)
    return tuple(windows)


def discover_windows(directory: Path, label: str) -> list[WindowFile]:
    """Every ``<label>_<window>.db`` in one folder; an unknown window id is an error."""
    if not directory.is_dir():
        raise DeliveryError(f"--dir {directory}: not a directory")
    prefix = f"{label}_"
    windows: list[WindowFile] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or not path.name.startswith(prefix) or not path.name.endswith(".db"):
            continue
        window = path.name[len(prefix) : -len(".db")]
        if window not in ALLOWED_WINDOW_SET:
            raise DeliveryError(
                f"{path.name}: unknown window {window!r}; allowed windows are "
                f"{', '.join(FINAL_WINDOWS)}"
            )
        windows.append(WindowFile(path.resolve(), window, label))
    if not windows:
        raise DeliveryError(
            f"--dir {directory}: no {label}_<window>.db file; allowed windows are "
            f"{', '.join(FINAL_WINDOWS)}"
        )
    return windows


def read_manifest(path: Path) -> Manifest:
    """Parse ``SHA256SUMS`` (64 hex digits, two spaces, file name) into lowercase hashes."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"{path}: {exc}") from exc
    entries: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        match = _HASH_LINE.fullmatch(line)
        if match is None:
            raise ManifestError(
                f"{path}:{number}: not a sha256sum line (64 hex digits, two spaces, file name): "
                f"{line!r}"
            )
        name = match.group("name").removeprefix("*")
        if not name:
            raise ManifestError(f"{path}:{number}: the manifest line has no file name")
        if name in entries:
            raise ManifestError(f"{path}:{number}: {name} is listed twice")
        entries[name] = match.group("hash").lower()
    if not entries:
        raise ManifestError(f"{path}: the manifest is empty")
    return Manifest(path, entries)


def hash_file(
    path: Path,
    *,
    chunk_size: int = CHUNK_SIZE,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[str, float]:
    """Stream one file through SHA-256 in ``chunk_size`` chunks; print its size and time."""
    if not path.is_file():
        raise ManifestError(f"missing file: {path}")
    digest = hashlib.sha256()
    size = path.stat().st_size
    started = clock()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    elapsed = clock() - started
    print(f"  hashed {path.name}: {size:,} bytes in {elapsed:.1f} s")
    return digest.hexdigest(), elapsed


def verify_manifest(
    manifest: Manifest,
    paths: Sequence[Path],
    *,
    hasher: Callable[[Path], tuple[str, float]] = hash_file,
) -> dict[Path, str]:
    """Hash every database to load and compare it with the manifest; return lowercase hashes."""
    print(f"\nmanifest: {manifest.path}")
    verified: dict[Path, str] = {}
    for database in paths:
        if not database.is_file():
            raise ManifestError(f"missing file: {database}")
        expected = manifest.entries.get(database.name)
        if expected is None:
            raise ManifestError(
                f"{database.name}: no entry in {manifest.path}; every database to load needs its "
                "SHA256SUMS line"
            )
        actual, _ = hasher(database)
        if actual.lower() != expected.lower():
            raise ManifestError(
                f"{database.name}: SHA-256 mismatch: manifest {expected}, actual {actual}"
            )
        verified[database] = actual.lower()
    print(f"manifest: {len(verified)} file(s) verified")
    return verified


def _scalar(value: str) -> str:
    """A YAML-ish scalar as a string; matching surrounding quotes are removed, nothing is typed."""
    if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _front_matter(  # noqa: C901 -- one branch per front-matter failure
    path: Path, text: str
) -> tuple[dict[str, str], str]:
    """Split ``---`` front matter from the body; the body keeps every byte after the separator."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ConfigError(f"{path}: the file does not start with a '---' front matter")
    closing = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if closing is None:
        raise ConfigError(f"{path}: the front matter has no closing '---'")
    values: dict[str, str] = {}
    for number, line in enumerate(lines[1:closing], 2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise ConfigError(f"{path}:{number}: expected 'key: value': {line.rstrip()!r}")
        key, value = key.strip(), value.strip()
        if not key:
            raise ConfigError(f"{path}:{number}: empty front-matter key")
        if key in values:
            raise ConfigError(f"{path}:{number}: {key} is given twice")
        values[key] = _scalar(value)
    body = "".join(lines[closing + 1 :])
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    if not body.strip():
        raise ConfigError(f"{path}: the configuration body is empty")
    return values, body


def read_config(path: Path, label: str) -> RunConfig:
    """Read ``config_<label>.md``: required/optional keys, string scalars and the verbatim body."""
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            text = handle.read()
    except OSError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    values, body = _front_matter(path, text)
    missing = [key for key in _REQUIRED_KEYS if not values.get(key)]
    if missing:
        raise ConfigError(f"{path}: missing required key(s): {', '.join(missing)}")
    if values["label"] != label:
        raise ConfigError(
            f"{path}: front-matter label {values['label']!r} differs from --label {label!r}"
        )
    if path.name != f"config_{label}.md":
        raise ConfigError(f"{path}: the file name must be config_{label}.md for --label {label!r}")
    warnings = tuple(
        f"{path}: unknown key {key!r} ignored"
        for key in values
        if key not in _REQUIRED_KEYS and key not in _OPTIONAL_KEYS
    )
    return RunConfig(
        path=path,
        label=label,
        code_commit=values["code_commit"],
        pr=values["pr"],
        results_doc=values["results_doc"],
        config_id=values.get("config_id") or None,
        status=values.get("status") or None,
        body=body,
        warnings=warnings,
    )


def load_config(path: Path, label: str) -> tuple[RunConfig, list[str]]:
    """Compatibility wrapper: the parsed configuration and its unknown-key warnings."""
    config = read_config(path, label)
    return config, list(config.warnings)


def _date(value: object, where: str) -> str:
    text = str(value)
    if not _DATE.fullmatch(text):
        raise DeliveryError(f"{where}: {text!r} is not a YYYY-MM-DD date")
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        raise DeliveryError(f"{where}: {text!r} is not a real date") from None
    return text


def _integer(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DeliveryError(f"{where}: {value!r} is not an integer")
    if value < 1:
        raise DeliveryError(f"{where}: {value!r} is not a positive integer")
    return value


@dataclass(frozen=True)
class WindowSource:
    """One window database after discovery, manifest verification and ``v_book`` reading."""

    window: str
    path: Path
    date_from: str
    date_to: str
    run_id: int
    knowledge_date: str
    sha256: str | None = None
    configuration: str | None = None


@dataclass
class Delivery:
    """A verified delivery: its chronologically ordered windows, manifest and configuration."""

    label: str
    folder: Path | None
    windows: list[WindowSource]
    manifest: dict[str, str] | None = None
    config: RunConfig | None = None
    warnings: tuple[str, ...] = ()

    @property
    def metadata(self) -> bool:
        """True when both the manifest and the configuration are present."""
        return self.manifest is not None and self.config is not None


def parse_windows(values: Sequence[str]) -> tuple[str, ...] | None:
    """Parse ``--windows`` (repeatable and comma-separated) into the required window set."""
    windows: list[str] = []
    for value in values:
        for window in window_sequence(value):
            if window not in windows:
                windows.append(window)
    return tuple(windows) if windows else None


def _filename_window(label: str, path: Path) -> str | None:
    """The window in ``<label>_<window>.db``; None for a legacy name (``a.db``)."""
    prefix = f"{label}_"
    if not path.name.startswith(prefix) or not path.name.endswith(".db"):
        return None
    window = path.name[len(prefix) : -len(".db")]
    if window not in ALLOWED_WINDOW_SET:
        raise DeliveryError(
            f"{path.name}: unknown window {window!r}; allowed windows are "
            f"{', '.join(FINAL_WINDOWS)}"
        )
    return window


def _directory_paths(label: str, directory: Path) -> list[Path]:
    return [window.path for window in discover_windows(directory, label)]


def _paths(label: str, databases: Sequence[Path], directories: Sequence[Path]) -> list[Path]:
    """Every database to load, from ``--dir`` discovery and explicit ``--db`` paths."""
    paths: list[Path] = []
    for directory in (Path(directory).resolve() for directory in directories):
        paths.extend(_directory_paths(label, directory))
    paths.extend(path.resolve() for path in databases)
    repeated = sorted({str(path) for path in paths if paths.count(path) > 1})
    if repeated:
        raise DeliveryError("database given twice: " + ", ".join(repeated))
    if not paths:
        raise DeliveryError(
            f"no {label}_<window>.db file and no --db PATH: allowed windows are "
            f"{', '.join(FINAL_WINDOWS)}"
        )
    for path in paths:
        _filename_window(label, path)
    return paths


def _folder(directories: Sequence[Path], paths: Sequence[Path], *, delivery: bool) -> Path | None:
    """The one folder the delivery files live in, or None when the inputs are spread out."""
    resolved = [Path(directory).resolve() for directory in directories]
    if len(set(resolved)) > 1:
        if delivery:
            raise DeliveryError(
                "a delivery uses one --dir folder for its manifest and configuration"
            )
        return None
    if resolved:
        return resolved[0]
    parents = {path.parent for path in paths}
    if len(parents) == 1:
        return next(iter(parents))
    if delivery:
        raise DeliveryError(
            "a delivery uses databases from one folder (or one --dir) so its manifest and "
            "configuration can be found"
        )
    return None


def _window_source(label: str, path: Path) -> WindowSource:
    """The ordered-window view of one database, read after its manifest entry was verified."""
    source = FinancialSource.open(path)
    try:
        rows = read_view(source, "v_book")
    finally:
        source.close()
    if not rows:
        raise DeliveryError(f"{path}: v_book is empty; not a completed backtest database")
    windows = {str(row.get("window_id")) for row in rows}
    if len(windows) != 1:
        raise DeliveryError(
            f"{path}: v_book has {len(windows)} distinct window_id values; one database is one window"
        )
    window = next(iter(windows))
    if window not in ALLOWED_WINDOW_SET:
        raise DeliveryError(
            f"{path}: window_id {window!r} is not one of {', '.join(FINAL_WINDOWS)}"
        )
    runs = {_integer(row.get("backtest_run_id"), f"{path}: v_book") for row in rows}
    if len(runs) != 1:
        raise DeliveryError(
            f"{path}: v_book has {len(runs)} distinct backtest_run_id values; one database is one run"
        )
    dates = {str(row.get("knowledge_date")) for row in rows}
    if len(dates) != 1:
        raise DeliveryError(
            f"{path}: v_book has {len(dates)} distinct knowledge_date values; one database is one "
            "knowledge date"
        )
    knowledge = _date(next(iter(dates)), f"{path}: v_book.knowledge_date")
    ranges = {
        (
            _date(row.get("d_start"), f"{path}: v_book.d_start"),
            _date(row.get("d_end"), f"{path}: v_book.d_end"),
        )
        for row in rows
    }
    if len(ranges) != 1:
        raise DeliveryError(
            f"{path}: v_book has {len(ranges)} distinct date ranges; one database is one window"
        )
    date_from, date_to = next(iter(ranges))
    if date_to < date_from:
        raise DeliveryError(f"{path}: v_book.d_end {date_to} is before d_start {date_from}")
    return WindowSource(window, path, date_from, date_to, next(iter(runs)), knowledge)


def load_delivery(  # noqa: C901, PLR0912, PLR0913 -- the delivery inputs are explicit
    label: str,
    databases: Sequence[Path],
    directories: Sequence[Path],
    required_windows: tuple[str, ...] | None,
    *,
    no_manifest: bool,
    no_config: bool,
    hasher: Callable[[Path], tuple[str, float]] = hash_file,
) -> Delivery:
    """Discover, hash-verify and read one delivery; no store is contacted."""
    if no_manifest != no_config:
        raise DeliveryError(
            "--no-manifest and --no-config go together: the metadata graph needs both a verified "
            "SHA256SUMS and a config_<label>.md"
        )
    delivery_mode = not (no_manifest and no_config)
    paths = _paths(label, databases, directories)
    folder = _folder(directories, paths, delivery=delivery_mode)
    manifest: dict[str, str] | None = None
    config: RunConfig | None = None
    warnings: list[str] = []
    if delivery_mode:
        assert folder is not None  # _folder raises for a delivery without one folder
        manifest_file = folder / MANIFEST_NAME
        config_file = config_path(folder, label)
        if not manifest_file.is_file():
            raise DeliveryError(
                f"{manifest_file}: missing; use --no-manifest --no-config only for a pilot "
                "folder without delivery files"
            )
        if not config_file.is_file():
            raise DeliveryError(
                f"{config_file}: missing; use --no-manifest --no-config only for a pilot "
                "folder without delivery files"
            )
        parsed = read_manifest(manifest_file)
        manifest = dict(parsed.entries)
        verified = verify_manifest(parsed, paths, hasher=hasher)
        config = read_config(config_file, label)
        warnings = list(config.warnings)
    else:
        verified = {}
        if folder is not None:
            present = [
                path
                for path in (folder / MANIFEST_NAME, config_path(folder, label))
                if path.exists()
            ]
            if present:
                raise DeliveryError(
                    "--no-manifest/--no-config cannot ignore a present delivery file: "
                    + ", ".join(str(path) for path in present)
                )
        print(
            "\nWARNING: pilot mode (--no-manifest --no-config): no SHA256SUMS and no "
            f"config_{label}.md; the metadata graph will not be built. The m018 and selection "
            "graphs are loaded as before.",
            file=sys.stderr,
        )
    windows = [_window_source(label, path) for path in paths]
    duplicated = sorted(
        {
            window.window
            for window in windows
            if [other.window for other in windows].count(window.window) > 1
        }
    )
    if duplicated:
        raise DeliveryError("two databases describe window(s) " + ", ".join(duplicated))
    for window in windows:
        expected = _filename_window(label, window.path)
        if delivery_mode and (
            expected is None or window.path.name != f"{label}_{window.window}.db"
        ):
            raise DeliveryError(
                f"{window.path.name}: a delivery file is named <label>_<window>.db "
                f"({label}_{window.window}.db expected)"
            )
        if expected is not None and expected != window.window:
            raise DeliveryError(
                f"{window.path.name}: the file name says window {expected!r} but v_book says "
                f"{window.window!r}"
            )
    if required_windows is not None:
        found = {window.window for window in windows}
        missing = [window for window in required_windows if window not in found]
        if missing:
            raise DeliveryError(
                f"--windows: no database for {', '.join(missing)}; found {', '.join(sorted(found))}"
            )
    windows.sort(key=lambda window: (window.date_from, window.date_to, window.window))
    windows = [
        WindowSource(
            window=window.window,
            path=window.path,
            date_from=window.date_from,
            date_to=window.date_to,
            run_id=window.run_id,
            knowledge_date=window.knowledge_date,
            sha256=verified.get(window.path),
        )
        for window in windows
    ]
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print("\nwindow order (chronological by v_book.d_start/d_end):")
    for window in windows:
        print(
            f"  {window.window}: {window.date_from}..{window.date_to}  "
            f"run {window.run_id}  {window.path.name}"
        )
    return Delivery(label, folder, windows, manifest, config, tuple(warnings))
