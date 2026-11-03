"""Check ``schema/fibo_terms.csv`` against the pinned FIBO release (T-210).

FIBO is a reference vocabulary, not a dependency (``docs/06`` §1.1): our terms stay in
``https://thesis.local/kg/portfolio#`` and the only link is ``rdfs:seeAlso``. This module is the
Phase 1 check that every ``fibo_iri`` in the terms file really exists in the pinned
``prod.ttl.zip`` release with an ``rdfs:label`` and a ``skos:definition``.

The zip is not committed (it is 1.4 MB and 134,946 statements), so this is not part of the hermetic
test suite by default: ``tests/test_fibo_terms.py`` exercises the logic over a tiny synthetic zip,
and ``cli/check_fibo_terms.py`` runs it against the real release. The sha256 pin is checked first,
so a different release is refused rather than silently accepted.

Placement: :mod:`projection` already holds the external-contract checks (:mod:`projection.source`,
:mod:`projection.contract_check`, :mod:`projection.expectations`); this is the FIBO side of the
same kind of check, so no fourth package is introduced (constitution Project structure #3).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import rdflib
from rdflib import Namespace
from rdflib.namespace import RDFS
from rdflib.term import Literal, URIRef

FIBO_BASE = "https://spec.edmcouncil.org/fibo/ontology/"
OUR_NAMESPACE = "https://thesis.local/kg/portfolio#"
#: FIBO 2026Q2, ``prod.ttl.zip`` (the brief §3/P2 pin; the release is never committed).
PINNED_SHA256 = "7a4ccebc9ff5c1e202bf1ae44928d9149a5f6f8ff1289dde42edff13e601f579"
FITS = frozenset({"same", "broader"})
HEADER = ("fibo_iri", "our_term", "fit", "label_es", "definition_es")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")


class FiboTermsError(ValueError):
    """The terms file, the release or an argument cannot be used; the message names which."""


class HashMismatch(FiboTermsError):
    """The zip is not the pinned FIBO release."""


@dataclass(frozen=True)
class Term:
    """One row of ``schema/fibo_terms.csv``."""

    fibo_iri: str
    our_term: str
    fit: str
    label_es: str
    definition_es: str


@dataclass(frozen=True)
class ReleaseTerm:
    """What the release says about one FIBO IRI; labels/definitions may come from several modules."""

    iri: str
    labels: tuple[Literal, ...]
    definitions: tuple[Literal, ...]

    @property
    def label(self) -> str:
        """The label to print: an untagged label first, then ``@en``, then any other."""
        ordered = sorted(
            self.labels,
            key=lambda literal: (
                0 if literal.language is None else 1 if literal.language == "en" else 2,
                str(literal),
            ),
        )
        return str(ordered[0])


@dataclass(frozen=True)
class CheckResult:
    """The terms, the release's entries and the rows that failed."""

    terms: tuple[Term, ...]
    found: Mapping[str, ReleaseTerm]
    failures: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.failures


def sha256(path: str | Path) -> str:
    """The zip's SHA-256, read in chunks so a larger release does not sit in memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_terms(path: str | Path) -> tuple[Term, ...]:
    """Read and validate the terms file; every bad row is named in the error.

    Phase 1 leaves ``label_es``/``definition_es`` empty; Phase 2 fills them. They are not required
    here, so the same file can carry the authors' Spanish text later without changing this check.
    """
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(HEADER):
            raise FiboTermsError(
                f"{path}: the header must be {','.join(HEADER)}, got {reader.fieldnames}"
            )
        rows = list(reader)
    if not rows:
        raise FiboTermsError(f"{path}: no data rows")
    terms: list[Term] = []
    seen: set[str] = set()
    for number, row in enumerate(rows, 2):
        term = Term(
            (row["fibo_iri"] or "").strip(),
            (row["our_term"] or "").strip(),
            (row["fit"] or "").strip(),
            (row["label_es"] or "").strip(),
            (row["definition_es"] or "").strip(),
        )
        where = f"{path}:{number}"
        if not term.fibo_iri.startswith(FIBO_BASE):
            raise FiboTermsError(f"{where}: fibo_iri {term.fibo_iri!r} is not under {FIBO_BASE}")
        if "/master/" in term.fibo_iri:
            raise FiboTermsError(f"{where}: fibo_iri {term.fibo_iri!r} carries a /master/ segment")
        if term.fit not in FITS:
            raise FiboTermsError(f"{where}: fit {term.fit!r} is not one of {sorted(FITS)}")
        if not term.our_term.startswith(OUR_NAMESPACE):
            raise FiboTermsError(
                f"{where}: our_term {term.our_term!r} is not under {OUR_NAMESPACE}"
            )
        if term.fibo_iri in seen:
            raise FiboTermsError(f"{where}: duplicate fibo_iri {term.fibo_iri!r}")
        seen.add(term.fibo_iri)
        terms.append(term)
    return tuple(terms)


def _modules(archive: zipfile.ZipFile) -> list[str]:
    return sorted(name for name in archive.namelist() if name.endswith(".ttl"))


def load_release(zip_path: str | Path, iris: Sequence[str]) -> dict[str, ReleaseTerm]:
    """Every label/definition the release's Turtle modules carry for ``iris``.

    Modules are parsed one at a time and only the six requested IRIs are kept, so the peak memory
    is one module rather than the whole 134,946-statement release. An IRI may be described in more
    than one module (``:Portfolio`` is), so the values are collected across all of them.
    """
    wanted = {URIRef(iri) for iri in iris}
    labels: dict[str, list[Literal]] = {iri: [] for iri in iris}
    definitions: dict[str, list[Literal]] = {iri: [] for iri in iris}
    path = Path(zip_path)
    if not zipfile.is_zipfile(path):
        raise FiboTermsError(f"{path}: not a zip file")
    with zipfile.ZipFile(path) as archive:
        modules = _modules(archive)
        if not modules:
            raise FiboTermsError(f"{path}: no Turtle modules")
        for name in modules:
            try:
                graph = rdflib.Graph().parse(data=archive.read(name), format="turtle")
            except Exception as exc:  # rdflib raises several parser-specific exceptions
                raise FiboTermsError(f"{path}: {name} does not parse as Turtle: {exc}") from exc
            for iri in wanted:
                labels[str(iri)].extend(
                    value for value in graph.objects(iri, RDFS.label) if isinstance(value, Literal)
                )
                definitions[str(iri)].extend(
                    value
                    for value in graph.objects(iri, SKOS.definition)
                    if isinstance(value, Literal)
                )
    return {
        iri: ReleaseTerm(
            iri,
            tuple(sorted(labels[iri], key=str)),
            tuple(sorted(definitions[iri], key=str)),
        )
        for iri in iris
    }


def check_release(
    zip_path: str | Path,
    terms_path: str | Path,
    *,
    expected_sha256: str = PINNED_SHA256,
) -> CheckResult:
    """Verify the pin, read the terms and check every IRI's label and definition.

    ``expected_sha256`` is a parameter so the hermetic tests can accept a synthetic zip; the CLI
    always passes the pinned value.
    """
    path = Path(zip_path)
    if not path.is_file():
        raise FiboTermsError(f"{path}: not a file")
    actual = sha256(path)
    if actual != expected_sha256:
        raise HashMismatch(
            f"{path}: sha256 {actual} is not the pinned {expected_sha256}; refusing the release"
        )
    terms = read_terms(terms_path)
    found = load_release(path, [term.fibo_iri for term in terms])
    failures: list[str] = []
    for term in terms:
        release_term = found[term.fibo_iri]
        if not release_term.labels and not release_term.definitions:
            failures.append(f"{term.fibo_iri}: missing from the release")
            continue
        if not release_term.labels:
            failures.append(f"{term.fibo_iri}: no rdfs:label in the release")
        if not release_term.definitions:
            failures.append(f"{term.fibo_iri}: no skos:definition in the release")
    return CheckResult(terms, found, tuple(failures))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--zip", required=True, type=Path, metavar="PATH", help="prod.ttl.zip")
    parser.add_argument(
        "--terms",
        required=True,
        type=Path,
        metavar="PATH",
        help="schema/fibo_terms.csv (or another file with the same header)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """0 when all terms pass, 1 on a check failure, 2 on a bad argument."""
    args = parse_args(argv)
    if not args.zip.is_file():
        print(f"bad argument: --zip {args.zip} is not a file", file=sys.stderr)
        return 2
    if not args.terms.is_file():
        print(f"bad argument: --terms {args.terms} is not a file", file=sys.stderr)
        return 2
    try:
        result = check_release(args.zip, args.terms)
    except FiboTermsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for term in result.terms:
        release_term = result.found[term.fibo_iri]
        label = release_term.label if release_term.labels else "MISSING"
        print(f"{term.fibo_iri} -> {label}")
    for failure in result.failures:
        print(failure, file=__import__("sys").stderr)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
