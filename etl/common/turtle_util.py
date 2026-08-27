"""Minimal, dependency-free Turtle-literal helpers.

Deliberately NOT using rdflib to build the multi-million-triple instance graph
in memory -- rdflib's Graph/serialize path is far slower and far more
memory-hungry than just emitting well-formed Turtle strings directly, and at
this row count (400K+ articles) that difference matters. rdflib IS still used
elsewhere (:mod:`etl.build_data_ttl`) for the small-sample SHACL validation
pass, where correctness-checking, not throughput, is the goal.
"""

from __future__ import annotations

import re

_ESCAPE_RE = re.compile(r'["\\\n\r\t]')
_ESCAPE_MAP = {'"': '\\"', "\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def esc(value: str) -> str:
    """Escape a Python string for use inside a Turtle double-quoted literal."""
    return _ESCAPE_RE.sub(lambda m: _ESCAPE_MAP[m.group(0)], value)


def str_lit(value: str) -> str:
    """Render ``value`` as a plain Turtle string literal."""
    return f'"{esc(value)}"'


def date_lit(value: str) -> str:
    """Render an already-valid ``xsd:date`` lexical form, e.g. ``2023-01-25``."""
    return f'"{value}"^^xsd:date'


def datetime_lit(value: str) -> str:
    """Render an already-valid ``xsd:dateTime`` lexical form."""
    return f'"{value}"^^xsd:dateTime'


def decimal_lit(value: float) -> str:
    """Render ``value`` as an ``xsd:decimal`` literal."""
    return f'"{value}"^^xsd:decimal'


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp ``value`` into the closed interval ``[lo, hi]``."""
    return max(lo, min(hi, value))
