"""The Talk to Your Graph sources stay reviewable and true (Work item 40/T-757).

Hermetic: the committed CONSTRUCT, the instructions, the evaluation sheet and the schema files are
the units under test. No GraphDB repository and no Workbench agent are contacted.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import rdflib
from rdflib.plugins.sparql import prepareQuery

REPO = Path(__file__).resolve().parent.parent
TTYG = REPO / "docs" / "ttyg"
CONSTRUCT = TTYG / "ontology_construct_curated_v3.rq"
INSTRUCTIONS = TTYG / "instructions-v1.3.md"
README = TTYG / "README.md"
CREATE_AGENT = TTYG / "create-agent.md"
EVALUATION = TTYG / "evaluation-questions.md"
TBOX = REPO / "schema" / "tbox.ttl"
LABELS = REPO / "schema" / "labels.ttl"
REFERENCE = REPO / "schema" / "reference.ttl"
RULES = REPO / "schema" / "rules.ttl"

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

#: Configuration facts the instructions may state; they are not result figures.
ALLOWED_CONFIG_NUMBERS = {"756", "210", "200", "100", "129"}

#: Result figures that must never be frozen into the instructions.
FORBIDDEN_RESULT_FIGURES = (
    "4,958",
    "978",
    "933",
    "603",
    "441",
    "714",
    "1,289",
    "734",
    "1007",
    "5,036",
    "509,933",
    "834,586",
)


def _instruction_block() -> str:
    """The one pasteable ``text`` fence of the instructions file."""
    text = INSTRUCTIONS.read_text(encoding="utf-8")
    matches = list(TEXT_FENCE.finditer(text))
    assert len(matches) == 1
    block = matches[0].group("block")
    assert isinstance(block, str)
    return block


def _construct_graph() -> rdflib.Graph:
    query = prepareQuery(CONSTRUCT.read_text(encoding="utf-8"))
    dataset = rdflib.Dataset()
    dataset.graph("urn:graph:tbox").parse(str(TBOX), format="turtle")
    dataset.graph("urn:graph:labels").parse(str(LABELS), format="turtle")
    dataset.graph("urn:graph:reference").parse(str(REFERENCE), format="turtle")
    dataset.graph("urn:graph:rules:catalog").parse(str(RULES), format="turtle")
    result = dataset.query(query)
    constructed = result.graph
    assert constructed is not None
    return constructed


def test_construct_parses_and_returns_the_curated_classes() -> None:
    # Work item 40, T-664/T-757: the source note says 29 classes; this asserts the measured count.
    constructed = _construct_graph()
    classes = {
        subject
        for subject, predicate, obj in constructed
        if predicate == rdflib.RDF.type and obj == rdflib.OWL.Class
    }

    assert len(classes) == 29
    for name in (
        "StrategyBook",
        "ReferenceReturn",
        "SECFiling",
        "FundamentalMetricSet",
        "FundamentalAssessment",
    ):
        assert rdflib.URIRef(f"https://thesis.local/kg/portfolio#{name}") in classes


def test_construct_exposes_the_fundamentals_properties_and_labels() -> None:
    constructed = _construct_graph()
    KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
    RDFS = rdflib.Namespace("http://www.w3.org/2000/01/rdf-schema#")
    SKOS = rdflib.Namespace("http://www.w3.org/2004/02/skos/core#")

    roic = KG.returnOnInvestedCapital
    assert (roic, rdflib.RDF.type, rdflib.OWL.DatatypeProperty) in constructed
    assert (roic, RDFS.domain, KG.FundamentalMetricSet) in constructed
    assert (
        roic,
        RDFS.label,
        rdflib.Literal("Return on invested capital", lang="en"),
    ) in constructed
    assert (KG.pricesNotPublished, RDFS.domain, KG.Asset) in constructed
    assert (KG.metricSetOfFiling, RDFS.domain, KG.FundamentalMetricSet) in constructed
    assert (KG.assessmentOfFiling, RDFS.domain, KG.FundamentalAssessment) in constructed

    concept = KG.FundamentalMetric_return_on_invested_capital
    assert (concept, rdflib.RDF.type, SKOS.Concept) in constructed
    assert (concept, SKOS.notation, rdflib.Literal("return_on_invested_capital")) in constructed
    assert (
        concept,
        RDFS.label,
        rdflib.Literal("Retorno sobre el capital invertido", lang="es"),
    ) in constructed
    assert (concept, KG.metricUnit, rdflib.Literal("ratio")) in constructed
    assert (concept, KG.labelScheme, KG.PresentationScheme) in constructed

    # The label vocabulary, rule labels and MetricType labels are part of the summary.
    assert (
        KG.Config_satellite_weighting,
        SKOS.notation,
        rdflib.Literal("satellite_weighting"),
    ) in (constructed)
    assert (KG.ScoreFinanciero, SKOS.prefLabel, rdflib.Literal("ScoreFinanciero", lang="es")) in (
        constructed
    )
    assert (KG.ScoreFinanciero, KG.labelScheme, KG.PresentationScheme) not in constructed
    rule = KG.Rule_LEVERAGE_EXTREME
    assert (rule, rdflib.RDF.type, KG.RuleDefinition) in constructed
    assert (rule, KG.ruleId, rdflib.Literal("LEVERAGE_EXTREME")) in constructed
    assert (rule, RDFS.label, rdflib.Literal("Extreme leverage", lang="en")) in constructed

    concepts = {
        subject
        for subject, predicate, obj in constructed
        if predicate == rdflib.RDF.type and obj == SKOS.Concept
    }
    schemes = {
        subject
        for subject, predicate, obj in constructed
        if predicate == rdflib.RDF.type and obj == SKOS.ConceptScheme
    }
    rules = {
        subject
        for subject, predicate, obj in constructed
        if predicate == rdflib.RDF.type and obj == KG.RuleDefinition
    }
    assert len(concepts) == 132
    assert len(schemes) == 12
    assert len(rules) == 24


def test_pasteable_block_carries_the_v1_3_rules() -> None:
    # Work item 40/T-757: the block is the source of truth for the Workbench agent.
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
    assert "not in the knowledge base used" in block
    assert "urn:graph:labels" in block
    assert "returnOnInvestedCapital" in block
    assert "marketCapitalization" in block
    assert "pricesNotPublished" in block
    assert "Tiingo" in block
    assert "generatedByLanguageModel false" in block
    assert "minimum CVaR" in block
    assert "1.5 divided by" in block
    assert "RunConfiguration_final" in block
    assert ":bookWeightingRule" in block
    assert "score_tilt" in block
    assert "rank_e" in block
    assert "QUERY HYGIENE" in block
    assert "tickerSymbol" in block
    assert "GRAPH <urn:graph:reference>" in block
    assert "unbounded" in block or "unbound" in block
    assert "MARKOWITZ_MV" in block
    assert "MARKOWITZ_BASE is a code only" in block
    assert "no :ScoreSnapshot link" in block
    assert "Interpretación generada por un modelo de lenguaje el 3 de noviembre de 2026" in block
    assert "Interpretation generated by a language model on 3 November 2026" in block
    assert "turnover" in block.lower()
    assert "prior fiscal-year-end balance" in block
    for date in WINDOW_DATES:
        assert date in block

    assert "Respondes en espanol" not in block
    assert "Respondes en español" not in block


def test_pasteable_block_has_no_result_figures() -> None:
    # Work item 40, T-664: no backtest figure may be frozen into the instructions.
    block = _instruction_block()
    without_dates = re.sub(r"\d{4}-\d{2}-\d{2}", "", block)
    without_years = re.sub(r"\b(?:19|20)\d{2}\b", "", without_dates)
    without_index_name = without_years.replace("S&P 500", "")

    assert re.search(r"\b\d{1,3}(?:,\d{3})+\b", without_index_name) is None
    numbers = set(re.findall(r"\b\d{3,}\b", without_index_name))
    assert numbers <= ALLOWED_CONFIG_NUMBERS, numbers
    for figure in FORBIDDEN_RESULT_FIGURES:
        assert figure not in block


def test_readme_records_the_construct_sha256_and_the_agent_form() -> None:
    # Work item 40, T-664: the hash is the record of the byte-identical copy.
    digest = hashlib.sha256(CONSTRUCT.read_bytes()).hexdigest()
    readme = README.read_text(encoding="utf-8")

    assert digest in readme
    assert "SPARQL only" in readme
    assert "0.1" in readme
    assert "Additional instructions" in readme
    assert "read-only user" in readme
    assert "ontology_construct_curated_v3.rq" in readme
    assert "instructions-v1.3.md" in readme
    assert "evaluation-questions.md" in readme
    assert "29" in readme


def test_create_agent_doc_links_the_sources_and_keeps_the_key_placeholder() -> None:
    """Work item 42 (T-722): the Workbench recipe links the current sources and never a real key."""
    text = CREATE_AGENT.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    assert "ontology_construct_curated_v3.rq" in text
    assert "instructions-v1.3.md" in text
    assert "graphdb.llm.api-key" in text
    assert "<YOUR_LLM_API_KEY>" in text
    assert "0.1" in text
    assert "DeepSeek" in text and "Gemini 3.x" in text
    assert "create-agent.md" in readme


def test_evaluation_sheet_has_the_t_758_and_t_757_questions() -> None:
    text = EVALUATION.read_text(encoding="utf-8")
    assert "The 16-question sheet" in text
    assert "T-757 additions" in text
    for phrase in (
        "ROIC",
        "market capitalisation",
        "pricesNotPublished",
        "Tiingo",
        "minimum CVaR",
        "1.5 divided by",
        "earliest `:availableAt`",
        "Turnover ratios",
        "Interpretación generada",
        "¿Cuál es el ROIC de Apple?",
        "tickerSymbol",
        "no full scan",
    ):
        assert phrase in text
