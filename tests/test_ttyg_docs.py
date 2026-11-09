"""The Talk to Your Graph sources stay reviewable and true (Work item 40, T-660-T-669).

Hermetic: the committed CONSTRUCT, the instructions and ``schema/tbox.ttl`` are the units under
test. No GraphDB repository and no Workbench agent are contacted.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import rdflib
from rdflib.plugins.sparql import prepareQuery

REPO = Path(__file__).resolve().parent.parent
TTYG = REPO / "docs" / "ttyg"
CONSTRUCT = TTYG / "ontology_construct_curated_v2.rq"
INSTRUCTIONS = TTYG / "instructions-v1.2.md"
README = TTYG / "README.md"
CREATE_AGENT = TTYG / "create-agent.md"
TBOX = REPO / "schema" / "tbox.ttl"

TEXT_FENCE = re.compile(r"```text\n(?P<block>.*?)```", re.DOTALL)

#: The six windows of the final delivery, in calendar order (A2).
WINDOW_DATES = (
    "2022-01-03",
    "2022-10-12",
    "2022-10-13",
    "2023-10-26",
    "2023-10-27",
    "2024-08-02",
    "2024-08-05",
    "2025-02-18",
    "2025-02-19",
    "2025-09-23",
    "2025-09-24",
    "2026-10-15",
)


def _instruction_block() -> str:
    """The one pasteable ``text`` fence of the instructions file."""
    text = INSTRUCTIONS.read_text(encoding="utf-8")
    matches = list(TEXT_FENCE.finditer(text))
    assert len(matches) == 1
    block = matches[0].group("block")
    assert isinstance(block, str)
    return block


def test_construct_parses_and_returns_the_curated_classes() -> None:
    # Work item 40, T-664: the source note says 26 classes; this asserts the measured count.
    query = prepareQuery(CONSTRUCT.read_text(encoding="utf-8"))
    dataset = rdflib.Dataset()
    dataset.graph("urn:graph:tbox").parse(str(TBOX), format="turtle")

    result = dataset.query(query)
    constructed = result.graph
    assert constructed is not None

    classes = {
        subject
        for subject, predicate, obj in constructed
        if predicate == rdflib.RDF.type and obj == rdflib.OWL.Class
    }

    assert len(classes) == 26
    assert rdflib.URIRef("https://thesis.local/kg/portfolio#StrategyBook") in classes
    assert rdflib.URIRef("https://thesis.local/kg/portfolio#ReferenceReturn") in classes


def test_pasteable_block_carries_the_v1_2_rules() -> None:
    # Work item 40, T-664: the block is the source of truth for the Workbench agent.
    block = _instruction_block()

    assert 'The default run label is "final"' in block
    assert (
        "The default counting rule is: rows whose date lies inside the window's own date range"
        in block
    )
    assert "language requested by the final line of the question" in block
    assert "in-sample" in block
    assert "min_var" in block
    assert "order them by date, never by name" in block
    for date in WINDOW_DATES:
        assert date in block

    assert "Respondes en espanol" not in block
    assert "Respondes en español" not in block


def test_pasteable_block_has_no_result_figures() -> None:
    # Work item 40, T-664: no backtest figure may be frozen into the instructions.
    block = _instruction_block()
    without_dates = re.sub(r"\d{4}-\d{2}-\d{2}", "", block)
    without_index_name = without_dates.replace("S&P 500", "")

    assert re.search(r"\b\d{1,3}(?:,\d{3})+\b", without_index_name) is None
    assert re.search(r"\b\d{3,}\b", without_index_name) is None


def test_readme_records_the_construct_sha256_and_the_agent_form() -> None:
    # Work item 40, T-664: the hash is the record of the byte-identical copy.
    digest = hashlib.sha256(CONSTRUCT.read_bytes()).hexdigest()
    readme = README.read_text(encoding="utf-8")

    assert digest in readme
    assert "SPARQL only" in readme
    assert "0.1" in readme
    assert "Additional instructions" in readme
    assert "read-only user" in readme


def test_create_agent_doc_links_the_sources_and_keeps_the_key_placeholder() -> None:
    """Work item 42 (T-722): the Workbench recipe links the two sources and never a real key."""
    text = CREATE_AGENT.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    assert "ontology_construct_curated_v2.rq" in text
    assert "instructions-v1.2.md" in text
    assert "graphdb.llm.api-key" in text
    assert "<YOUR_LLM_API_KEY>" in text
    assert "0.1" in text
    assert "DeepSeek" in text and "Gemini 3.x" in text
    assert "create-agent.md" in readme
