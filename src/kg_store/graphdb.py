"""Minimal GraphDB REST client: connection settings from the environment, HTTP Basic auth.

Settings are ``KG_HOST``, ``KG_REPOSITORY``, ``KG_USER`` and ``KG_PASSWORD`` (see
``.env.example``), read from the process environment or the repo-root ``.env`` via
``python-dotenv``. Credentials are only ever placed in the ``Authorization`` header;
they are never logged or included in an error message.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent
load_dotenv(REPO_ROOT / ".env", override=False)

#: Named graph holding explicit (asserted) statements, as opposed to inferred ones.
EXPLICIT_GRAPH = "http://www.ontotext.com/explicit"


class GraphDBError(RuntimeError):
    """A GraphDB request failed (status code and response body, never credentials)."""


@dataclass(frozen=True)
class GraphDB:
    host: str
    repository: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> GraphDB:
        host = os.environ.get("KG_HOST", "").rstrip("/")
        repository = os.environ.get("KG_REPOSITORY", "")
        if host and not host.startswith(("http://", "https://")):
            raise GraphDBError("KG_HOST must start with http:// or https://")
        missing = [k for k, v in (("KG_HOST", host), ("KG_REPOSITORY", repository)) if not v]
        if missing:
            raise GraphDBError(f"set {', '.join(missing)} (see .env.example)")
        return cls(
            host, repository, os.environ.get("KG_USER", ""), os.environ.get("KG_PASSWORD", "")
        )

    @property
    def _repo_url(self) -> str:
        return f"{self.host}/repositories/{urllib.parse.quote(self.repository)}"

    def _request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        content_type: str | None = None,
        accept: str | None = None,
    ) -> bytes:
        req = urllib.request.Request(url, data=body, method=method)  # noqa: S310 -- scheme checked in from_env
        if self.user:
            token = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
            req.add_header("Authorization", f"Basic {token}")
        if content_type:
            req.add_header("Content-Type", content_type)
        if accept:
            req.add_header("Accept", accept)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 -- scheme checked in from_env
                payload: bytes = resp.read()
                return payload
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise GraphDBError(
                f"{method} {urllib.parse.urlsplit(url).path} -> HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise GraphDBError(f"cannot reach GraphDB at {self.host}: {exc.reason}") from exc

    def update(self, sparql: str) -> None:
        """Run a SPARQL Update (needs write access)."""
        body = urllib.parse.urlencode({"update": sparql}).encode()
        self._request(
            "POST", f"{self._repo_url}/statements", body, "application/x-www-form-urlencoded"
        )

    def select(self, sparql: str) -> list[dict[str, str]]:
        """Run a SPARQL SELECT; each row maps variable name to its lexical value."""
        body = urllib.parse.urlencode({"query": sparql}).encode()
        raw = self._request(
            "POST",
            self._repo_url,
            body,
            "application/x-www-form-urlencoded",
            "application/sparql-results+json",
        )
        rows = json.loads(raw)["results"]["bindings"]
        return [{k: v["value"] for k, v in row.items()} for row in rows]

    def add(self, data: bytes, content_type: str, graph: str | None = None) -> None:
        """Append RDF to the store: into ``graph`` if given, else as quads (TriG)."""
        url = f"{self._repo_url}/statements"
        if graph:
            url += "?" + urllib.parse.urlencode({"context": f"<{graph}>"})
        self._request("POST", url, data, content_type)

    def explicit_graph_sizes(self) -> dict[str, int]:
        """Asserted triple count per named graph (inferred statements excluded)."""
        rows = self.select(
            f"SELECT ?g (COUNT(*) AS ?n) FROM <{EXPLICIT_GRAPH}> WHERE {{ GRAPH ?g {{ ?s ?p ?o }} }} GROUP BY ?g"  # noqa: S608 -- constant IRI, no user input
        )
        return {r["g"]: int(r["n"]) for r in rows}
