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

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
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


def ticker_cik_map(rows: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """A symbol -> CIK map from ``v_ticker_history`` rows, omitting an ambiguous symbol.

    Both the historical ``symbol`` and the row's ``canonical_symbol`` are keys, because a view
    row's ticker can be either (``FBHS`` and ``FBIN`` both point at CIK ``0001519751``). A symbol
    carried by two different CIKs over time is removed rather than guessed; the caller then treats
    it as having no CIK and the asset link stays unset unless the exact symbol is loaded.
    """
    ciks: dict[str, str] = {}
    conflicts: set[str] = set()
    for row in rows:
        cik = row.get("cik")
        if not isinstance(cik, str) or not cik:
            continue
        for column in ("symbol", "canonical_symbol"):
            symbol = row.get(column)
            if not isinstance(symbol, str) or not symbol:
                continue
            previous = ciks.get(symbol)
            if previous is not None and previous != cik:
                conflicts.add(symbol)
            else:
                ciks[symbol] = cik
    for symbol in conflicts:
        ciks.pop(symbol, None)
    return ciks
