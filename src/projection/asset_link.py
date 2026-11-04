"""Resolve an upstream ticker to a loaded ``:Asset`` without inventing one (T-351).

The ticker a view carries is not always the IRI the asset catalog uses. The catalog is one
``:Asset`` per company line (T-264), named by the latest symbol the loader saw; when the company
renamed after the catalog's last kept stint, the view's canonical symbol (``FBIN``) is newer than
the catalog's IRI (``:FBHS``). The same happens for ``GAP``/``:GPS``. Both rows still share one
CIK, so the company line is unambiguous even though the symbols differ.

The rule is deliberately narrow:

1. an exact symbol match wins (``META`` -> ``:META``);
2. otherwise, exactly one loaded ``:Asset`` carrying the row's CIK wins (``FBIN`` -> ``:FBHS``);
3. otherwise nothing is linked. No match, several same-CIK assets (concurrent classes, a mixed
   CIK), or no CIK means the caller leaves the property unset and counts the row.

This module is shared with the selection projector (Work item 26), which hit the same
``FBIN``/``GAP`` rows. It never creates an ``:Asset`` and never links across CIKs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from projection.backtest import AssetInfo

#: How a link was resolved: the exact symbol, the unique same-CIK fallback, or no safe link.
LinkKind = Literal["symbol", "cik", "none"]


@dataclass(frozen=True)
class AssetLink:
    """The loaded asset a symbol resolves to, and the rule that resolved it."""

    iri: str | None
    how: LinkKind


def resolve_asset(symbol: str, cik: str | None, assets: Mapping[str, AssetInfo]) -> AssetLink:
    """Resolve ``symbol`` to a loaded asset IRI, using the row's CIK only when it is unique."""
    if symbol in assets:
        return AssetLink(symbol, "symbol")
    if cik:
        matches = sorted(name for name, info in assets.items() if info.cik == cik)
        if len(matches) == 1:
            return AssetLink(matches[0], "cik")
    return AssetLink(None, "none")
