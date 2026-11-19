"""The Talk to Your Graph sources stay reviewable and true (Work item 40/T-757; T-760-T-762).

Hermetic: the committed CONSTRUCTs, the instructions, the evaluation sheet, the delivery notes and
the schema files are the units under test. No GraphDB repository and no Workbench agent are
contacted.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import rdflib
from rdflib.plugins.sparql import prepareQuery
from rdflib.term import Node

REPO = Path(__file__).resolve().parent.parent
TTYG = REPO / "docs" / "ttyg"
CONSTRUCT_V2_1 = TTYG / "ontology_construct_curated_v2_1.rq"
CONSTRUCT_V3 = TTYG / "ontology_construct_curated_v3.rq"
INSTRUCTIONS = TTYG / "instructions-v1.5.md"
INSTRUCTIONS_V17 = TTYG / "instructions-v1.7.md"
INSTRUCTIONS_LIVE = TTYG / "instructions-live-v1.md"
SUPERSEDED_INSTRUCTIONS = TTYG / "instructions-v1.4.md"
README = TTYG / "README.md"
CREATE_AGENT = TTYG / "create-agent.md"
EVALUATION = TTYG / "evaluation-questions.md"
FINAL_DELIVERY = REPO / "docs" / "final-delivery.md"
TASKS = REPO / ".specify" / "memory" / "TASKS.md"
PLAN = REPO / ".specify" / "memory" / "PLAN.md"
TBOX = REPO / "schema" / "tbox.ttl"
LABELS = REPO / "schema" / "labels.ttl"
REFERENCE = REPO / "schema" / "reference.ttl"
RULES = REPO / "schema" / "rules.ttl"

#: The byte-exact copy of the only CONSTRUCT the Workbench form accepted on 2026-11-14.
V2_1_SHA256 = "9f0b96af7427583015fbec1e0d59ce411c95db000d8173940454143c606bdc64"

TEXT_FENCE = re.compile(r"```text\n(?P<block>.*?)```", re.DOTALL)
QUESTION_PATTERN = re.compile(
    r"\nPATTERN \d+ - [^\n]+\n(?P<query>.*?)(?=\nPATTERN \d+ - |\n\nWHAT IS NOT)",
    re.DOTALL,
)

#: The six calendar windows of the final delivery, in calendar order (A2).
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
    "271",
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


def _instruction_block(path: Path = INSTRUCTIONS) -> str:
    """The one pasteable ``text`` fence of the instructions file."""
    text = path.read_text(encoding="utf-8")
    matches = list(TEXT_FENCE.finditer(text))
    assert len(matches) == 1
    block = matches[0].group("block")
    assert isinstance(block, str)
    return block


def _construct_graph(construct: Path = CONSTRUCT_V2_1) -> rdflib.Graph:
    query = prepareQuery(construct.read_text(encoding="utf-8"))
    dataset = rdflib.Dataset()
    dataset.graph("urn:graph:tbox").parse(str(TBOX), format="turtle")
    dataset.graph("urn:graph:labels").parse(str(LABELS), format="turtle")
    dataset.graph("urn:graph:reference").parse(str(REFERENCE), format="turtle")
    dataset.graph("urn:graph:rules:catalog").parse(str(RULES), format="turtle")
    result = dataset.query(query)
    constructed = result.graph
    assert constructed is not None
    return constructed


def _classes(constructed: rdflib.Graph) -> set[Node]:
    return {
        subject
        for subject, predicate, obj in constructed
        if predicate == rdflib.RDF.type and obj == rdflib.OWL.Class
    }


def test_v2_1_is_the_byte_exact_workbench_construct() -> None:
    # T-761: the form rejects v3; v2.1 is the reviewed file and must stay byte-identical.
    assert hashlib.sha256(CONSTRUCT_V2_1.read_bytes()).hexdigest() == V2_1_SHA256
    readme = README.read_text(encoding="utf-8")
    assert V2_1_SHA256 in readme
    assert "ontology_construct_curated_v2_1.rq" in readme
    assert "not pasteable" in readme.lower()
    assert "2,271 bytes" in readme


def test_v2_1_parses_and_returns_the_agent_classes_and_roic() -> None:
    # T-761: the accepted CONSTRUCT still exposes the classes and the ROIC property.
    constructed = _construct_graph(CONSTRUCT_V2_1)
    classes = _classes(constructed)
    KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
    RDFS = rdflib.Namespace("http://www.w3.org/2000/01/rdf-schema#")

    assert len(classes) == 29
    for name in (
        "SECFiling",
        "FundamentalMetricSet",
        "FundamentalAssessment",
        "Veto",
        "GuardAlert",
    ):
        assert KG[name] in classes

    roic = KG.returnOnInvestedCapital
    assert (roic, rdflib.RDF.type, rdflib.OWL.DatatypeProperty) in constructed
    assert (roic, RDFS.domain, KG.FundamentalMetricSet) in constructed


def test_v3_reference_construct_parses_and_returns_the_curated_classes() -> None:
    # Work item 40, T-664/T-757: v3 stays as the review/test reference; this asserts its count.
    constructed = _construct_graph(CONSTRUCT_V3)
    classes = _classes(constructed)
    KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")

    assert len(classes) == 29
    for name in (
        "StrategyBook",
        "ReferenceReturn",
        "SECFiling",
        "FundamentalMetricSet",
        "FundamentalAssessment",
    ):
        assert KG[name] in classes


def test_v3_reference_construct_exposes_the_fundamentals_properties_and_labels() -> None:
    constructed = _construct_graph(CONSTRUCT_V3)
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
    assert len(concepts) == 161
    assert len(schemes) == 12
    assert len(rules) == 24


def test_pasteable_block_carries_the_v1_5_rules() -> None:  # noqa: PLR0915
    # T-760: the block is the source of truth for the Workbench agent.
    block = _instruction_block()

    assert "Start with the datum itself" in block
    assert 'Never open with "Yes, it is in the knowledge base used"' in block
    assert "For a fundamentals or conceptual answer, omit the backtest boilerplate" in block
    assert "The counting rule must state exactly the filter" in block
    assert (
        "The default counting rule is: rows whose date lies inside the window's own date range"
        in (block)
    )
    assert "replace every D in the sentence" in block
    assert "never a veto" in block
    assert "BREAK_TREND_200" in block
    assert "do not list all loaded windows" in block
    assert 'The default run label is "final"' in block
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
    assert "VALUES ?tg { <urn:graph:reference> <urn:graph:universe:2026-Q4> }" in block
    assert "GRAPH ?tg" in block
    assert "unbounded" in block or "unbound" in block
    assert "MARKOWITZ_MV" in block
    assert "MARKOWITZ_BASE is never called that" in block
    assert "final book is TOPN_MV_GUARD" in block
    assert "urn:graph:derived:news:final:{year" in block
    assert 'item_kind is "sub_news"' in block
    assert "a body has no :articleId or :sourceDomain" in block
    assert "its title may be empty" in block
    assert "urn:graph:derived:backtest:agents:final:{window}" in block
    assert "urn:graph:derived:backtest:aggregates:final" in block
    assert "urn:graph:derived:backtest:series:final:{spy|markowitz_mv}" in block
    assert ":newsRiskOff" in block
    assert "no :ScoreSnapshot link" in block
    assert "Interpretación generada por un modelo de lenguaje el 3 de noviembre de 2026" in block
    assert "Interpretation generated by a language model on 3 November 2026" in block
    assert "turnover" in block.lower()
    assert "prior fiscal-year-end balance" in block
    assert "QUESTION PATTERNS" in block
    for date in WINDOW_DATES:
        assert date in block

    # T-760/T-761: the five delivered configurations and the continuous C1 window.
    for name in (
        "SYSTEM_WITH_HIERARCHY",
        "SYSTEM_WITHOUT_HIERARCHY",
        "MARKOWITZ_BASE",
        "MARKOWITZ_MV",
        "SPY",
    ):
        assert name in block
    assert "continuous window C1 is 2022-01-03..2026-10-15" in block
    assert "MARKOWITZ_BASE_GUARD" not in block

    # The stale/internal wording must not come back into the pasteable block.
    for stale in ("block C", "Work item", "warm-up vetoes", "value_inputs", "v3 name"):
        assert stale not in block
    assert re.search(r"\bT-\d{3,4}\b", block) is None
    assert re.search(r"\bPR #\d+", block) is None

    assert "Respondes en espanol" not in block
    assert "Respondes en español" not in block


def test_question_patterns_are_bounded_and_parseable() -> None:
    # T-760: 6-8 small skeletons, each at most about 600 characters.
    block = _instruction_block()
    patterns = [match.group("query") for match in QUESTION_PATTERN.finditer(block)]
    prefixes = (
        "PREFIX : <https://thesis.local/kg/portfolio#>\n"
        "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
    )
    assert 6 <= len(patterns) <= 8
    for query in patterns:
        assert len(query) <= 650
        assert "GRAPH" in query
        assert re.search(r"\bLIMIT\s+\d+", query, re.IGNORECASE)
        prepareQuery(prefixes + query)


def test_ticker_question_patterns_search_both_graphs() -> None:
    # T-760 review: seed assets are in urn:graph:reference, catalog assets in the universe graph.
    block = _instruction_block()
    patterns = [match.group("query") for match in QUESTION_PATTERN.finditer(block)]
    ticker_patterns = [query for query in patterns if ":tickerSymbol" in query]
    both_graphs = re.compile(
        r"VALUES\s+\?tg\s*\{\s*<urn:graph:reference>\s+<urn:graph:universe:2026-Q4>\s*\}"
    )
    assert len(ticker_patterns) == 4
    for query in ticker_patterns:
        assert both_graphs.search(query)
        assert "GRAPH ?tg" in query
        assert "GRAPH <urn:graph:reference>" not in query
        assert "GRAPH <urn:graph:universe:2026-Q4>" not in query


def test_fundamental_question_patterns_use_the_derived_graph() -> None:
    # T-760 review: the store's fundamentals graph is urn:graph:derived:fundamentals:final.
    block = _instruction_block()
    patterns = [match.group("query") for match in QUESTION_PATTERN.finditer(block)]
    fundamental_patterns = [
        query
        for query in patterns
        if ":returnOnInvestedCapital" in query or ":assessmentOfAsset" in query
    ]
    assert len(fundamental_patterns) == 2
    for query in fundamental_patterns:
        assert "GRAPH <urn:graph:derived:fundamentals:final>" in query
        assert "GRAPH <urn:graph:fundamentals:final>" not in query


def test_pasteable_block_has_no_result_figures() -> None:
    # Work item 40, T-664: no backtest figure may be frozen into the instructions.
    block = _instruction_block()
    without_dates = re.sub(r"\d{4}-\d{2}-\d{2}", "", block)
    without_years = re.sub(r"\b(?:19|20)\d{2}\b", "", without_dates)
    without_index_name = without_years.replace("S&P 500", "").replace("2,000", "")

    assert re.search(r"\b\d{1,3}(?:,\d{3})+\b", without_index_name) is None
    numbers = set(re.findall(r"\b\d{3,}\b", without_index_name))
    assert numbers <= ALLOWED_CONFIG_NUMBERS, numbers
    for figure in FORBIDDEN_RESULT_FIGURES:
        assert figure not in block


def test_the_recipes_review_and_recording_template_are_complete() -> None:
    review = (TTYG / "recipes-review-final.md").read_text(encoding="utf-8")
    for case in [f"C{number}" for number in range(1, 21)] + [
        f"R{number}" for number in range(1, 10)
    ]:
        assert f"| {case} |" in review
    template = (TTYG / "evaluation-recording-template.csv").read_text(encoding="utf-8").splitlines()
    assert template[0].split(",") == [
        "case_id",
        "question_sent",
        "attempt_number",
        "answer",
        "generated_sparql",
        "configuration_and_window",
        "identification",
        "accuracy",
        "context",
        "honesty",
        "notes",
    ]
    assert len(template) == 30
    assert [line.split(",", 1)[0] for line in template[1:]] == [
        f"C{number}" for number in range(1, 21)
    ] + [f"R{number}" for number in range(1, 10)]


def test_readme_records_the_construct_sha256_and_the_agent_form() -> None:
    # Work item 40, T-664/T-761: the hash is the record of the byte-identical copy.
    digest = hashlib.sha256(CONSTRUCT_V2_1.read_bytes()).hexdigest()
    readme = README.read_text(encoding="utf-8")

    assert digest in readme
    assert "SPARQL only" in readme
    assert "0.1" in readme
    assert "Additional instructions" in readme
    assert "read-only user" in readme
    assert "ontology_construct_curated_v2_1.rq" in readme
    assert "instructions-v1.5.md" in readme
    assert "instructions-v1.7.md" in readme
    assert "evaluation-questions.md" in readme
    assert "29" in readme


def test_create_agent_doc_links_the_sources_and_keeps_the_key_placeholder() -> None:
    """Work item 42 (T-722)/T-761: the recipe links the current sources and never a real key."""
    text = CREATE_AGENT.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    block = _instruction_block(INSTRUCTIONS_V17)

    assert "ontology_construct_curated_v2_1.rq" in text
    assert "instructions-v1.7.md" in text
    assert "portfolio-final-v1-7" in text
    assert "Auto-add missing namespaces" in text
    assert "**Ticked.**" in text
    assert "Review agent instructions" in text
    assert len(block.rstrip("\n")) == 37_611
    assert "37,611 characters" in text
    assert "37,612" in text
    assert "portfolio_test" in text
    assert "`portfolio`" in text
    assert "scratch folder" in text and "different GUARD rules" in text
    assert "graphdb.llm.api-key" in text
    assert "<YOUR_LLM_API_KEY>" in text
    assert "0.1" in text
    assert "DeepSeek" in text and "Gemini 3.x" in text
    assert "create-agent.md" in readme


def test_live_agent_instructions_are_bounded_and_leave_out_the_final_delivery() -> None:
    text = INSTRUCTIONS_LIVE.read_text(encoding="utf-8")
    block = _instruction_block(INSTRUCTIONS_LIVE)
    assert len(block.rstrip("\n")) <= 37_611
    assert len(block.rstrip("\n")) > 5_000
    assert "portfolio-live-v1" in text
    assert "repository **`portfolio_live`**" in text
    assert "create-agent.md" in text
    assert "SYSTEM_LIVE" in block
    assert "portfolio_live" in block
    assert "three fixed" in text
    for forbidden in (
        "978",
        "271",
        "SYSTEM_WITH_HIERARCHY",
        "SYSTEM_WITHOUT_HIERARCHY",
        "MARKOWITZ_BASE",
        "MARKOWITZ_MV",
        "C1",
        "P1",
        "P2",
        "P3",
        "H1",
        "H2",
        "H3",
    ):
        assert forbidden not in block, forbidden
    assert "SPY series" in block
    assert "does not have" in block
    assert block.count("\nPATTERN ") == 6
    assert ":knowledgeDate of the live :BacktestRun" not in block
    assert "loaded day is the :BacktestRun's :knowledgeDate" not in block
    assert "date the run was created, not the loaded day" in block
    assert ":dateTo of the :PortfolioPeriodSummary" in block
    assert "weights belong to ?weightDate, not to the loaded day" in block
    assert "COALESCE(?asset, <urn:none:no-asset>)" in block
    assert ":stoppedAsset ?stopped" in block
    assert ":memoryAsset ?stopped" in block
    loader = (REPO / "docs" / "live-day-loader.md").read_text(encoding="utf-8")
    assert "The loaded day is the `:knowledgeDate`" not in loader
    assert "`:dateTo` of the live `:PortfolioPeriodSummary`" in loader


def test_second_user_setup_names_the_final_export_and_the_demo_agent() -> None:
    text = (REPO / "docs" / "second-user-setup.md").read_text(encoding="utf-8")
    for phrase in (
        "portfolio-final-20261117T154804Z",
        "12,727,091",
        "86 named graphs",
        "portfolio-final-v1-7",
        "instructions-v1.7.md",
        "v1.5",
        "Workbench → Import",
        "minutes, not seconds",
        "KG_CHAT_TIMEOUT_SECONDS=300",
        "271",
        "+73.1%",
        "live-day-loader.md",
        "v0.1.0-entrega1",
        "0d40b7bb40c793576ad6da9fdd514297bb3c6cc0",
        "KG_AGENT_ID",
        "portfolio_live",
        "NOT tested end to end",
    ):
        assert phrase in text, phrase
    assert "<pinned version>" not in text


def test_superseded_v1_4_is_marked_as_a_historical_copy() -> None:
    text = re.sub(r"\s+", " ", SUPERSEDED_INSTRUCTIONS.read_text(encoding="utf-8"))
    assert "Superseded by" in text
    assert "instructions-v1.5.md" in text
    assert "historical copy" in text


def test_evaluation_sheet_has_the_t_758_t_757_and_t_762_questions() -> None:
    text = re.sub(r"\s+", " ", EVALUATION.read_text(encoding="utf-8"))
    assert "The 16-question sheet" in text
    assert "T-757 additions" in text
    assert "T-762 additions" in text
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
        "C1 is a loaded window",
        "continuous window 2022-01-03..2026-10-15",
        "BREAK_TREND_200",
        "flag/indicator",
        "L1_BP_STOP",
        "The stated counting rule must be exactly the filter",
        "every occurrence of `D`",
        "first answers must start with the datum",
    ):
        assert phrase in text


def test_final_delivery_links_the_agent_and_records_the_pitfalls() -> None:
    # T-762: the production sequence ends with the manual agent step and the known pitfalls.
    text = FINAL_DELIVERY.read_text(encoding="utf-8")
    assert "### 8.5 Create the agent (manual)" in text
    assert "create-agent.md" in text
    assert "Repository ID `portfolio`" in text
    assert "Pilot rehearsal body" in text
    assert "questions 21 and 22" in text
    assert "## Known pitfalls (notes, not commands)" in text
    assert "SQL_UNIVERSE_DB" in text
    assert "docker start portfolio" in text
    assert "docker ps" in text


def test_v1_5_and_the_d4_tasks_are_recorded() -> None:
    tasks = TASKS.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for task in ("T-927", "T-928", "T-929"):
        assert f"**{task}**" in tasks
        assert f"**{task}**" in plan
    assert (TTYG / "instructions-v1.5.md").is_file()
    assert (TTYG / "instructions-v1.7.md").is_file()
    assert (TTYG / "recipes-review-final.md").is_file()
    assert (TTYG / "evaluation-recording-template.csv").is_file()


def test_work_item_43_records_the_review_fixes_and_keeps_t_759_open() -> None:
    # T-760-T-762 are done; T-759 is still the human run; the work item stays open.
    tasks = TASKS.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for task in ("T-760", "T-761", "T-762"):
        assert f"**{task}**" in tasks
        assert f"**{task}**" in plan
    assert "- [ ] **T-759**" in tasks
    assert "- [ ] **T-759**" in plan
    assert "T-763" in tasks and "T-779" in tasks
    assert "T-763" in plan and "T-779" in plan
