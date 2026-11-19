"""Read one ``manifest_live.json`` and adapt it to the Veto Hierarchy delivery (Work item 47).

The live operator exports one folder per day: ``manifest_live.json``, a ``SHA256SUMS`` of that
folder and the day's ranking/selection files. The engine database (about 3 GB) is cited by an
absolute path and a SHA-256, not copied. This module is deliberately only an adapter: it validates
the manifest's keys and types, verifies the folder's ``SHA256SUMS``, every ``files_sha256`` entry
and the declared database/mask hashes, then builds the same :class:`VetoManifest`,
:class:`ManifestRun` and :class:`RunConfig` the final loader uses, with the one live
configuration/window (``SYSTEM_LIVE``/``LIVE``) and label ``live``.

The projection, SHACL and gate code are not reimplemented here.
"""

from __future__ import annotations

import datetime
import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from projection.delivery import Manifest, ManifestError, RunConfig, read_manifest
from projection.veto_manifest import (
    LIVE_CONFIGURATION,
    ManifestRun,
    PriceMask,
    VetoManifest,
    VetoManifestError,
    backtest_graph_name,
    hash_file,
    meta_graph_name,
    selection_graph_name,
)

#: The live day's one label and window; the configuration is the shared SYSTEM_LIVE constant.
LIVE_LABEL = "live"
LIVE_WINDOW = "LIVE"

#: Staging graphs use their own label, so every name still comes from the shared helpers and the
#: live graph IRIs stay fixed. They are dropped by the swap.
STAGING_LABEL = "live_staging"

#: The folder-relative files of a live day, keyed by the manifest field that names them.
LIVE_FILE_FIELDS: tuple[str, ...] = (
    "rankings_file",
    "panels_file",
    "scales_file",
    "retention_file",
    "verification_file",
    "news_actions_file",
    "bull_mode_file",
    "manager_calls_file",
    "jsonl_file",
)

_REQUIRED_KEYS = frozenset(
    {
        "configuration",
        "window",
        "day",
        "formation",
        "run_id",
        "book_code",
        "book_id",
        "db_file",
        "db_sha256",
        "price_mask_file",
        "price_mask_sha256",
        "files_sha256",
        *LIVE_FILE_FIELDS,
    }
)
_OPTIONAL_KEYS = frozenset({"operator"})
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_MANIFEST_NAME = "manifest_live.json"
_SUMS_NAME = "SHA256SUMS"


class LiveManifestError(VetoManifestError):
    """The live folder, its manifest, or one of its hashes cannot be accepted."""


@dataclass(frozen=True)
class LiveManifest:
    """A verified live day, ready to be adapted to the final loader's types."""

    folder: Path
    path: Path
    day: str
    formation: str
    run_id: str
    book_code: str
    book_id: int
    operator: str | None
    db_file: Path
    db_sha256: str
    price_mask: PriceMask
    files: Mapping[str, Path]
    file_hashes: Mapping[Path, str]
    folder_hashes: Mapping[str, str]
    hashes: Mapping[Path, str]

    def veto_manifest(self) -> VetoManifest:
        """The one-run manifest the existing projection/SHACL code consumes."""
        run = ManifestRun(
            configuration=LIVE_CONFIGURATION,
            window=LIVE_WINDOW,
            db_file=self.db_file,
            db_sha256=self.db_sha256,
            # The manifest's run_id is an operator code (H1B-A2g-LIVE), not the engine's integer
            # v_book.backtest_run_id; the metadata graph reads that one from the database.
            run_id=1,
            book_code=self.book_code,
            book_id=self.book_id,
            source_kind="engine_db",
            files=self.files,
            file_hashes=self.file_hashes,
            code_version=self.operator,
        )
        return VetoManifest(
            path=self.path,
            root=self.folder,
            status=None,
            label=LIVE_LABEL,
            created_at=self.day,
            windows=(LIVE_WINDOW,),
            price_mask=self.price_mask,
            prereg={},
            configurations=(),
            runs=(run,),
            control_counts=None,
            news_rows=None,
            bull_mode_note=None,
        )

    def run_config(self) -> RunConfig:
        """The metadata graph's frozen configuration, synthesized from the live manifest."""
        operator = self.operator or "n/a"
        body = (
            f"SYSTEM_LIVE day {self.day} (formation {self.formation}); "
            f"run {self.run_id}; book {self.book_code} id {self.book_id}; operator {operator}."
        )
        return RunConfig(
            path=self.path,
            label=LIVE_LABEL,
            code_commit=operator,
            pr="n/a",
            results_doc="n/a",
            body=body,
            config_id=self.run_id,
            status=LIVE_WINDOW,
        )


def live_graph_name() -> str:
    """The one fixed m018 graph of SYSTEM_LIVE."""
    return backtest_graph_name(LIVE_LABEL, LIVE_WINDOW, LIVE_CONFIGURATION)


def live_selection_graph_name() -> str:
    """The one fixed selection graph of SYSTEM_LIVE."""
    return selection_graph_name(LIVE_LABEL, LIVE_WINDOW, LIVE_CONFIGURATION)


def live_meta_graph_name() -> str:
    """The one fixed metadata graph of SYSTEM_LIVE."""
    return meta_graph_name(LIVE_LABEL)


def live_graph_names() -> tuple[str, ...]:
    """The three live graphs, in the order the loader writes and verifies them."""
    return (live_meta_graph_name(), live_graph_name(), live_selection_graph_name())


def staging_graph_names() -> tuple[str, ...]:
    """The three staging graphs; each ``MOVE`` names one of them and its live counterpart."""
    return (
        meta_graph_name(STAGING_LABEL),
        backtest_graph_name(STAGING_LABEL, LIVE_WINDOW, LIVE_CONFIGURATION),
        selection_graph_name(STAGING_LABEL, LIVE_WINDOW, LIVE_CONFIGURATION),
    )


def read_live_manifest(folder: str | Path) -> LiveManifest:
    """Parse and verify one ``graph_export`` folder; no database is opened."""
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise LiveManifestError(f"{root}: not a directory")
    path = root / _MANIFEST_NAME
    raw = _read_json(path)
    _check_keys(raw, path)

    configuration = _text(raw, "configuration")
    if configuration != LIVE_CONFIGURATION:
        raise LiveManifestError(
            f"{path}: configuration {configuration!r} is not {LIVE_CONFIGURATION!r}"
        )
    window = _text(raw, "window")
    if window != LIVE_WINDOW:
        raise LiveManifestError(f"{path}: window {window!r} is not {LIVE_WINDOW!r}")
    day = _date(raw, "day")
    formation = _date(raw, "formation")
    if day < formation:
        raise LiveManifestError(f"{path}: day {day} is before formation {formation}")

    sums = _read_sums(root)
    folder_hashes = _verify_folder(root, sums, path)
    files, file_hashes = _files(root, raw, sums)

    db_file = _path(root, raw, "db_file")
    if not db_file.is_file():
        raise LiveManifestError(f"{path}: missing database: {db_file}")
    db_sha256 = _hash(raw, "db_sha256")
    actual_db = _hash_file(db_file, f"{path}: db_file")
    if actual_db != db_sha256:
        raise LiveManifestError(
            f"{db_file}: SHA-256 mismatch: manifest {db_sha256}, actual {actual_db}"
        )
    mask_file = _path(root, raw, "price_mask_file")
    if not mask_file.is_file():
        raise LiveManifestError(f"{path}: missing price mask: {mask_file}")
    mask_sha256 = _hash(raw, "price_mask_sha256")
    actual_mask = _hash_file(mask_file, f"{path}: price_mask_file")
    if actual_mask != mask_sha256:
        raise LiveManifestError(
            f"{mask_file}: SHA-256 mismatch: manifest {mask_sha256}, actual {actual_mask}"
        )

    hashes: dict[Path, str] = {db_file: actual_db, mask_file: actual_mask}
    for file_path in files.values():
        hashes[file_path] = folder_hashes[file_path.name]

    return LiveManifest(
        folder=root,
        path=path,
        day=day,
        formation=formation,
        run_id=_text(raw, "run_id"),
        book_code=_text(raw, "book_code"),
        book_id=_positive_int(raw, "book_id"),
        operator=_optional_text(raw, "operator"),
        db_file=db_file,
        db_sha256=db_sha256,
        price_mask=PriceMask(mask_file, mask_sha256, "SYSTEM_LIVE"),
        files=files,
        file_hashes=file_hashes,
        folder_hashes=folder_hashes,
        hashes=hashes,
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LiveManifestError(f"{path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LiveManifestError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise LiveManifestError(f"{path}: the manifest must be a JSON object")
    return raw


def _check_keys(raw: Mapping[str, Any], path: Path) -> None:
    unknown = sorted(set(raw) - _REQUIRED_KEYS - _OPTIONAL_KEYS)
    if unknown:
        raise LiveManifestError(f"{path}: unknown key(s): {', '.join(unknown)}")
    missing = sorted(_REQUIRED_KEYS - set(raw))
    if missing:
        raise LiveManifestError(f"{path}: missing key(s): {', '.join(missing)}")


def _read_sums(root: Path) -> Manifest:
    sums_path = root / _SUMS_NAME
    if not sums_path.is_file():
        raise LiveManifestError(f"{sums_path}: missing; the live folder must bring its SHA256SUMS")
    try:
        return read_manifest(sums_path)
    except ManifestError as exc:
        raise LiveManifestError(str(exc)) from exc


def _verify_folder(root: Path, sums: Manifest, manifest_path: Path) -> dict[str, str]:
    """Hash every file the folder's SHA256SUMS lists; it must list the manifest itself."""
    if _MANIFEST_NAME not in sums.entries:
        raise LiveManifestError(f"{sums.path}: does not list {_MANIFEST_NAME}")
    verified: dict[str, str] = {}
    for name, declared in sums.entries.items():
        path = _inside(root, name, f"{sums.path}: {name}")
        actual = _hash_file(path, f"{sums.path}: {name}")
        if actual != declared:
            raise LiveManifestError(
                f"{path}: SHA-256 mismatch: SHA256SUMS {declared}, actual {actual}"
            )
        verified[name] = actual
    return verified


def _files(
    root: Path, raw: Mapping[str, Any], sums: Manifest
) -> tuple[dict[str, Path], dict[Path, str]]:
    """Resolve the nine logical files and cross-check their two hash declarations."""
    declared = raw.get("files_sha256")
    if not isinstance(declared, dict):
        raise LiveManifestError("files_sha256 must be an object")
    unknown = sorted(set(declared) - set(LIVE_FILE_FIELDS))
    if unknown:
        raise LiveManifestError(f"files_sha256: unknown file key(s): {', '.join(unknown)}")
    missing = sorted(set(LIVE_FILE_FIELDS) - set(declared))
    if missing:
        raise LiveManifestError(f"files_sha256: missing file key(s): {', '.join(missing)}")

    files: dict[str, Path] = {}
    hashes: dict[Path, str] = {}
    for field in LIVE_FILE_FIELDS:
        name = _text(raw, field)
        if "/" in name or "\\" in name or name in (".", ".."):
            raise LiveManifestError(f"{field}: {name!r} must be one file name, not a path")
        path = _inside(root, name, field)
        if not path.is_file():
            raise LiveManifestError(f"{field}: missing file: {path}")
        digest = _hash(declared, field, where="files_sha256")
        folder_digest = sums.entries.get(name)
        if folder_digest is None:
            raise LiveManifestError(f"{sums.path}: does not list {name}")
        if digest != folder_digest:
            raise LiveManifestError(
                f"{name}: files_sha256 {digest} differs from SHA256SUMS {folder_digest}"
            )
        files[field] = path
        hashes[path] = digest
    return files, hashes


def _inside(root: Path, name: str, where: str) -> Path:
    path = (root / name).resolve()
    if path != root and root not in path.parents:
        raise LiveManifestError(f"{where}: {name!r} escapes the folder")
    return path


def _path(root: Path, raw: Mapping[str, Any], key: str) -> Path:
    value = _text(raw, key)
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else _inside(root, value, key)


def _text(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise LiveManifestError(f"{key} must be a non-empty string")
    return value


def _optional_text(raw: Mapping[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise LiveManifestError(f"{key} must be a non-empty string when present")
    return value


def _hash(raw: Mapping[str, Any], key: str, *, where: str | None = None) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise LiveManifestError(f"{where or key}: {value!r} is not a lowercase SHA-256")
    return value


def _positive_int(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LiveManifestError(f"{key}: {value!r} is not a positive integer")
    return value


def _date(raw: Mapping[str, Any], key: str) -> str:
    value = _text(raw, key)
    if not _DATE.fullmatch(value):
        raise LiveManifestError(f"{key}: {value!r} is not a YYYY-MM-DD date")
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        raise LiveManifestError(f"{key}: {value!r} is not a real date") from None
    return value


def _hash_file(path: Path, where: str) -> str:
    """Stream one file once, printing its size and elapsed time like the final loader."""
    size = path.stat().st_size
    started = time.perf_counter()
    try:
        digest = hash_file(path)
    except VetoManifestError as exc:
        raise LiveManifestError(f"{where}: {exc}") from exc
    print(f"  hashed {path.name}: {size:,} bytes in {time.perf_counter() - started:.1f} s")
    return digest
