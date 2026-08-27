"""Central configuration for the KG-population ETL.

Every path/URL the ETL needs is resolved here, in this precedence order:

1. an explicit argument passed by the caller (tests, ``build_data_ttl`` CLI),
2. an environment variable, loaded from a repo-root ``.env`` by ``python-dotenv``,
3. a documented default rooted at the repository.

The one value that has no useful default is ``URLS_DB`` -- the external
``news-collector`` SQLite database lives outside this repo (in this dev
container it is bind-mounted at ``/workspaces/thesis/data/urls.db``), so it
must be supplied via ``.env``. See ``.env.example`` and ``etl/README.md``.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

#: Repository root (the directory that contains ``schema/`` and ``.env``).
REPO_ROOT: Path = Path(__file__).resolve().parent.parent

# Load ``<repo>/.env`` if present. ``override=False`` keeps any value already
# exported in the real environment authoritative over the file.
load_dotenv(REPO_ROOT / ".env", override=False)

#: Default Wikipedia source for the S&P 500 constituent table.
DEFAULT_SP500_SOURCE_URL: str = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

#: Rows the validation-sample build in :mod:`etl.build_data_ttl` reads.
DEFAULT_SAMPLE_NEWS_ROWS: int = 500


def _env_path(var: str, default: Path) -> Path:
    """Return ``$var`` as an expanded :class:`~pathlib.Path`, else ``default``."""
    raw = os.environ.get(var)
    return Path(raw).expanduser() if raw else default


def schema_dir() -> Path:
    """Directory holding ``tbox.ttl``/``shapes.ttl``/``reference.ttl``/``rules.ttl``."""
    return _env_path("KG_SCHEMA_DIR", REPO_ROOT / "schema")


def urls_db_path() -> Path:
    """Path to the external ``news-collector`` SQLite database (``urls.db``)."""
    return _env_path("KG_URLS_DB", REPO_ROOT / "data" / "urls.db")


def output_path() -> Path:
    """Path the generated flat-Turtle dataset is written to (``data.ttl``)."""
    return _env_path("KG_DATA_TTL", REPO_ROOT / "data.ttl")


def sp500_source_url() -> str:
    """URL of the S&P 500 constituent table to parse for the ``:Asset`` population."""
    return os.environ.get("KG_SP500_SOURCE_URL", DEFAULT_SP500_SOURCE_URL)


def sample_news_rows() -> int:
    """Number of news rows to include in the post-build SHACL validation sample."""
    raw = os.environ.get("KG_SAMPLE_NEWS_ROWS")
    return int(raw) if raw else DEFAULT_SAMPLE_NEWS_ROWS
