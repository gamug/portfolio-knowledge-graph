"""Contract v18 ontology: 11 classes, their properties and SHACL shapes (T-206).

Hermetic, like ``tests/test_schema_gate.py``: the real ``schema/`` files are the unit under test.
The synthetic individuals below exercise every new shape, including each nullable case the handoff
§3.3 names, and the GUARD rule/veto separation the shape change introduced.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pyshacl
import pytest
import rdflib
import rdflib.collection
from rdflib.namespace import OWL, RDF, RDFS, SH, XSD

SCHEMA = Path(__file__).resolve().parent.parent / "schema"
KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
SKOS = rdflib.Namespace("http://www.w3.org/2004/02/skos/core#")

TURTLE_FILES = ("tbox.ttl", "shapes.ttl", "reference.ttl", "rules.ttl")


@pytest.fixture(scope="module")
def bundle() -> rdflib.Dataset:
    ds = rdflib.Dataset()
    for name in TURTLE_FILES:
        ds.parse(SCHEMA / name, format="turtle")
    ds.parse(SCHEMA / "instances.trig", format="trig")
    return ds


@pytest.fixture(scope="module")
def shapes() -> rdflib.Graph:
    return rdflib.Graph().parse(SCHEMA / "shapes.ttl", format="turtle")


@pytest.fixture(scope="module")
def tbox() -> rdflib.Graph:
    return rdflib.Graph().parse(SCHEMA / "tbox.ttl", format="turtle")


def _flat(ds: rdflib.Dataset) -> rdflib.Graph:
    g = rdflib.Graph()
    for s, p, o, _ in ds.quads():
        g.add((s, p, o))
    return g


def _violations(
    data: rdflib.Graph, shapes: rdflib.Graph
) -> set[tuple[rdflib.term.Node | None, rdflib.term.Node | None]]:
    conforms, results, _ = pyshacl.validate(data, shacl_graph=shapes, meta_shacl=True)
    assert isinstance(results, rdflib.Graph)
    found = {
        (results.value(r, SH.focusNode), results.value(r, SH.resultPath))
        for r in results.subjects(SH.focusNode, None)
    }
    assert conforms == (not found)
    return found


def _date(text: str) -> rdflib.Literal:
    return rdflib.Literal(text, datatype=XSD.date)


def _int(value: int) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.integer)


def _dec(value: str) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.decimal)


# --- the 11 classes and the handoff §6.2 Spanish text ------------------------------------------

NEW_CLASSES: dict[rdflib.URIRef, tuple[rdflib.URIRef, str, str]] = {
    KG.TickerHistory: (
        KG.TemporalRelation,
        "historial de símbolo bursátil",
        (
            "Registro histórico de cada símbolo bursátil (ticker) utilizado por una línea de emisor "
            "(identificada por su CIK en la SEC) durante un intervalo [validFrom, validTo]. Permite "
            "resolver el símbolo vigente en cada fecha histórica."
        ),
    ),
    KG.OrchestratorRun: (
        KG.Observation,
        "ejecución del orquestador",
        (
            "Registro de una corrida del orquestador del sistema (pipeline completo o comando "
            "individual), con su identificador de seguimiento (handle), fecha de corte (as_of), estado "
            "y configuración."
        ),
    ),
    KG.OrchestratorStep: (
        KG.Observation,
        "paso de ejecución del orquestador",
        (
            "Paso individual ejecutado dentro de una corrida del orquestador, con su orden, estado, "
            "tiempos de inicio y fin, código de salida y referencia al registro de corrida del "
            "subsistema correspondiente."
        ),
    ),
    KG.StrategyBook: (
        KG.Collection,
        "libro de estrategia de backtest",
        (
            "Brazo experimental de una corrida de backtest en una ventana histórica (P1, P2 o P3): "
            "MARKOWITZ_BASE (optimización de mínima varianza sobre todo el universo elegible sin "
            "selección de ciclo), TOPN_MV_NOGUARD (selección Top-30 del ciclo + mínima varianza sin "
            "GUARD) o TOPN_MV_GUARD_NO_NLP (selección Top-30 + mínima varianza con protección diaria "
            "GUARD activa)."
        ),
    ),
    KG.BookRebalance: (
        KG.TemporalRelation,
        "rebalanceo programado del libro",
        (
            "Rebalanceo periódico de un libro de estrategia (cada 21 sesiones de NYSE): vincula la "
            "fecha de decisión (cierre de t-1) y la fecha de ejecución (cierre de t) con el portafolio "
            "de Markowitz, el modelo de riesgo y la corrida de selección del ciclo."
        ),
    ),
    KG.GuardAlert: (
        KG.Observation,
        "alerta diaria de GUARD",
        (
            "Alerta de riesgo generada al cierre de una sesión por las capas de protección diaria "
            "GUARD: corte individual por pérdida acumulada (capa 1, L1_STOP_LOSS / L1_REENTRY), "
            "volatilidad ex-ante del portafolio (capa 3, L3_VOL) o caída acumulada desde el máximo "
            "(capa 4, L4_DD)."
        ),
    ),
    KG.GuardAction: (
        KG.RiskAndDecision,
        "acción de GUARD sobre un libro",
        (
            "Evaluación y efecto de una alerta de GUARD sobre un libro de estrategia para la sesión "
            "siguiente (effective_date): APPLIED (aplicada), ARM_DISABLED (registrada como contrafactual "
            "en el brazo sin GUARD), NOT_HELD (activo no mantenido en cartera) o SUPERSEDED."
        ),
    ),
    KG.BookWeightDaily: (
        KG.Observation,
        "peso de tenencia en el libro",
        (
            "Peso objetivo de un activo o de la posición en efectivo (CASH) dentro de un libro de "
            "estrategia en sus fechas de decisión y ejecución (peso objetivo de Markowitz y peso "
            "objetivo final tras GUARD)."
        ),
    ),
    KG.BookDailyPerformance: (
        KG.Observation,
        "desempeño diario del libro",
        (
            "Serie diaria a nivel de portafolio de un libro de estrategia: retorno bruto, rotación "
            "(turnover), costo de transacción (10 bps), retorno neto, valor liquidativo (NAV), caída "
            "desde el máximo (drawdown), peso en efectivo, número de acciones y retorno del índice "
            "equiponderado interno (SP500_EW_INTERNAL)."
        ),
    ),
    KG.PortfolioPeriodSummary: (
        KG.Observation,
        "resumen de desempeño por período",
        (
            "Estadísticas consolidadas de un libro de estrategia en una ventana o subperíodo de "
            "backtest (P1, P2, P2a, P2b, P3): retorno acumulado y anualizado, volatilidad anualizada, "
            "ratio de Sharpe ex-post sobre la tasa libre de riesgo diaria (FF_RF_DAILY), máximo "
            "drawdown, rotación total, costo total en puntos básicos, número de rebalanceos y número "
            "de acciones de GUARD."
        ),
    ),
    KG.BacktestTest: (
        KG.Observation,
        "prueba estadística pareada de backtest",
        (
            "Resultado de una prueba de hipótesis pareada entre dos brazos de estrategia en un "
            "segmento (Jobson-Korkie con corrección de Memmel, bootstrap en bloques de Ledoit-Wolf "
            "para el ratio de Sharpe y diferencia de medias diarias con errores estándar HAC de "
            "Newey-West): estadístico, valor p y número de sesiones."
        ),
    ),
}


def test_the_bundle_has_52_classes_and_39_disjoint_leaves(
    bundle: rdflib.Dataset,
) -> None:
    g = _flat(bundle)
    assert len(set(g.subjects(RDF.type, OWL.Class))) == 52
    members = set()
    for disjoint in g.subjects(RDF.type, OWL.AllDisjointClasses):
        for collection in g.objects(disjoint, OWL.members):
            members |= set(rdflib.collection.Collection(g, collection))
    assert len(members) == 39
    assert set(NEW_CLASSES) <= members


def test_each_new_class_has_one_spanish_label_and_definition(
    tbox: rdflib.Graph,
) -> None:
    for cls, (_, label, definition) in NEW_CLASSES.items():
        labels = [o for o in tbox.objects(cls, RDFS.label) if getattr(o, "language", None) == "es"]
        definitions = [
            o for o in tbox.objects(cls, SKOS.definition) if getattr(o, "language", None) == "es"
        ]
        assert [str(o) for o in labels] == [label], cls
        assert [str(o) for o in definitions] == [definition], cls
        assert any(
            getattr(o, "language", None) in (None, "en") for o in tbox.objects(cls, RDFS.label)
        )


def test_each_new_class_is_placed_under_its_backbone_class(tbox: rdflib.Graph) -> None:
    for cls, (parent, _, _) in NEW_CLASSES.items():
        assert (cls, RDFS.subClassOf, parent) in tbox, cls


def test_no_new_class_has_a_fibo_see_also(tbox: rdflib.Graph) -> None:
    for cls in NEW_CLASSES:
        assert (cls, RDFS.seeAlso, None) not in tbox, cls


# --- every column of the 11 views has a property ------------------------------------------------

VIEW_PROPERTIES: dict[str, tuple[str, ...]] = {
    "v_orchestrator_run": (
        "orchestratorRunId",
        "handle",
        "runKind",
        "runAsOf",
        "surface",
        "status",
        "startedAt",
        "finishedAt",
        "settingsJson",
        "codeVersion",
    ),
    "v_orchestrator_step": (
        "stepOfOrchestratorRun",
        "handle",
        "ordinal",
        "stepName",
        "status",
        "startedAt",
        "finishedAt",
        "exitCode",
        "runKind",
        "runId",
        "reason",
        "argvJson",
        "outputTail",
    ),
    "v_ticker_history": (
        "tickerHistoryCik",
        "historicalSymbol",
        "validFrom",
        "validTo",
        "canonicalSymbol",
        "tickerHistoryAsset",
        "evidenceUrl",
        "evidenceDate",
        "tickerHistoryRules",
    ),
    "v_book": (
        "bookId",
        "backtestRunId",
        "windowId",
        "backtestStartDate",
        "backtestEndDate",
        "formationDate",
        "runStatus",
        "armCode",
        "objective",
        "excludeHardVetoed",
        "guardLayers",
        "codeVersion",
        "knowledgeDate",
    ),
    "v_book_rebalance": (
        "rebalanceId",
        "bookId",
        "backtestRunId",
        "armCode",
        "decisionDate",
        "executionDate",
        "quantPortfolioId",
        "cycleRunId",
        "riskModelId",
        "status",
        "knowledgeDate",
    ),
    "v_guard_alert": (
        "alertId",
        "backtestRunId",
        "windowId",
        "alertDate",
        "guardLayer",
        "guardTicker",
        "guardAsset",
        "alertRule",
        "alertValue",
        "alertThreshold",
        "alertState",
        "knowledgeDate",
    ),
    "v_guard_action": (
        "actionId",
        "bookId",
        "backtestRunId",
        "armCode",
        "actionAlert",
        "decisionDate",
        "effectiveDate",
        "guardTicker",
        "guardAsset",
        "status",
        "weightBefore",
        "weightAfter",
        "knowledgeDate",
    ),
    "v_book_weight_daily": (
        "bookId",
        "backtestRunId",
        "armCode",
        "weightDate",
        "holdingKey",
        "holdingAsset",
        "holdingName",
        "markowitzTargetWeight",
        "finalTargetWeight",
        "knowledgeDate",
    ),
    "v_book_daily_performance": (
        "bookId",
        "backtestRunId",
        "armCode",
        "windowId",
        "performanceDate",
        "grossReturn",
        "turnover",
        "costReturn",
        "netReturn",
        "nav",
        "drawdown",
        "cashWeight",
        "nEquity",
        "benchmarkReturn",
        "knowledgeDate",
    ),
    "v_portfolio_period_summary": (
        "bookId",
        "backtestRunId",
        "armCode",
        "windowId",
        "segment",
        "dateFrom",
        "dateTo",
        "cumulativeReturn",
        "annualizedReturn",
        "annualizedVol",
        "exPostSharpe",
        "maxDrawdown",
        "totalTurnover",
        "totalCostBps",
        "nRebalances",
        "nGuardActions",
        "knowledgeDate",
    ),
    "v_backtest_test": (
        "backtestRunId",
        "windowId",
        "segment",
        "armA",
        "armB",
        "testName",
        "statistic",
        "pValue",
        "nObs",
        "paramsJson",
        "knowledgeDate",
    ),
}

SHARED_PROPERTIES = (
    "bookId",
    "backtestRunId",
    "armCode",
    "windowId",
    "runLabel",
    "knowledgeDate",
    "status",
    "decisionDate",
    "guardTicker",
    "guardLayer",
    "segment",
    "handle",
    "startedAt",
    "finishedAt",
    "runKind",
)


def test_every_new_view_column_has_a_declared_property(tbox: rdflib.Graph) -> None:
    for view, names in VIEW_PROPERTIES.items():
        for name in names:
            prop = KG[name]
            assert (prop, RDF.type, OWL.DatatypeProperty) in tbox or (
                prop,
                RDF.type,
                OWL.ObjectProperty,
            ) in tbox, f"{view}.{name}"


def test_shared_properties_have_no_domain(tbox: rdflib.Graph) -> None:
    """The :runId pattern: a domain would entail one disjoint class on another class's individual."""
    for name in SHARED_PROPERTIES:
        assert (KG[name], RDFS.domain, None) not in tbox, name


def test_the_new_shapes_are_34_named_shapes(shapes: rdflib.Graph) -> None:
    named = {s for s in shapes.subjects(RDF.type, SH.NodeShape) if isinstance(s, rdflib.URIRef)}
    assert len(named) == 34
    assert {
        KG.TickerHistoryShape,
        KG.OrchestratorRunShape,
        KG.OrchestratorStepShape,
        KG.StrategyBookShape,
        KG.BookRebalanceShape,
        KG.GuardAlertShape,
        KG.GuardActionShape,
        KG.BookWeightDailyShape,
        KG.BookDailyPerformanceShape,
        KG.PortfolioPeriodSummaryShape,
        KG.BacktestTestShape,
    } <= named


# --- synthetic m018 individuals ----------------------------------------------------------------

BOOK = KG.Book_T206
REBALANCE = KG.Rebalance_T206
ALERT = KG.Alert_T206
ACTION = KG.Action_T206
WEIGHT = KG.Weight_T206
PERFORMANCE = KG.Performance_T206
SUMMARY = KG.Summary_T206
TEST = KG.Test_T206
TICKER = KG.Ticker_T206
RUN = KG.OrchestratorRun_T206
STEP = KG.OrchestratorStep_T206
CASH_WEIGHT = KG.CashWeight_T206
L3_ALERT = KG.AlertL3_T206
L3_ACTION = KG.ActionL3_T206


def _add_book(g: rdflib.Graph) -> None:
    g.add((BOOK, RDF.type, KG.StrategyBook))
    g.add((BOOK, KG.bookId, _int(1)))
    g.add((BOOK, KG.backtestRunId, _int(1)))
    g.add((BOOK, KG.runLabel, rdflib.Literal("rule")))
    g.add((BOOK, KG.windowId, rdflib.Literal("P1")))
    g.add((BOOK, KG.backtestStartDate, _date("2022-01-03")))
    g.add((BOOK, KG.backtestEndDate, _date("2022-10-12")))
    g.add((BOOK, KG.runStatus, rdflib.Literal("completed")))
    g.add((BOOK, KG.armCode, rdflib.Literal("MARKOWITZ_BASE")))
    g.add((BOOK, KG.objective, rdflib.Literal("min_var")))
    g.add((BOOK, KG.excludeHardVetoed, rdflib.Literal(False)))
    g.add((BOOK, KG.knowledgeDate, _date("2026-11-01")))


def _add_rebalance(g: rdflib.Graph) -> None:
    # MARKOWITZ_BASE: cycle_run_id absent.
    g.add((REBALANCE, RDF.type, KG.BookRebalance))
    g.add((REBALANCE, KG.rebalanceOfBook, BOOK))
    g.add((REBALANCE, KG.rebalanceId, _int(1)))
    g.add((REBALANCE, KG.bookId, _int(1)))
    g.add((REBALANCE, KG.backtestRunId, _int(1)))
    g.add((REBALANCE, KG.armCode, rdflib.Literal("MARKOWITZ_BASE")))
    g.add((REBALANCE, KG.decisionDate, _date("2022-01-04")))
    g.add((REBALANCE, KG.executionDate, _date("2022-01-05")))
    g.add((REBALANCE, KG.status, rdflib.Literal("executed")))
    g.add((REBALANCE, KG.knowledgeDate, _date("2022-01-05")))


def _add_alerts(g: rdflib.Graph) -> None:
    # Layer 1: value absent, asset present.
    g.add((ALERT, RDF.type, KG.GuardAlert))
    g.add((ALERT, KG.alertId, _int(1)))
    g.add((ALERT, KG.backtestRunId, _int(1)))
    g.add((ALERT, KG.windowId, rdflib.Literal("P1")))
    g.add((ALERT, KG.alertDate, _date("2022-02-01")))
    g.add((ALERT, KG.guardLayer, _int(1)))
    g.add((ALERT, KG.alertRule, KG.Rule_L1_STOP_LOSS))
    g.add((ALERT, KG.alertThreshold, _dec("0.0")))
    g.add((ALERT, KG.alertState, rdflib.Literal("ENTER")))
    g.add((ALERT, KG.guardAsset, KG.AAPL))
    g.add((ALERT, KG.guardTicker, rdflib.Literal("AAPL")))
    g.add((ALERT, KG.knowledgeDate, _date("2022-02-01")))
    # Layer 3: asset/ticker absent, value present.
    g.add((L3_ALERT, RDF.type, KG.GuardAlert))
    g.add((L3_ALERT, KG.alertId, _int(2)))
    g.add((L3_ALERT, KG.backtestRunId, _int(1)))
    g.add((L3_ALERT, KG.windowId, rdflib.Literal("P1")))
    g.add((L3_ALERT, KG.alertDate, _date("2022-02-02")))
    g.add((L3_ALERT, KG.guardLayer, _int(3)))
    g.add((L3_ALERT, KG.alertRule, KG.Rule_L3_VOL))
    g.add((L3_ALERT, KG.alertValue, _dec("1.5")))
    g.add((L3_ALERT, KG.alertThreshold, _dec("0.2455")))
    g.add((L3_ALERT, KG.alertState, rdflib.Literal("SCALE")))
    g.add((L3_ALERT, KG.knowledgeDate, _date("2022-02-02")))


def _add_action(g: rdflib.Graph) -> None:
    # Layer 1 action: weight_before/after absent, asset present.
    g.add((ACTION, RDF.type, KG.GuardAction))
    g.add((ACTION, KG.actionId, _int(1)))
    g.add((ACTION, KG.bookId, _int(1)))
    g.add((ACTION, KG.actionOfBook, BOOK))
    g.add((ACTION, KG.actionAlert, ALERT))
    g.add((ACTION, KG.backtestRunId, _int(1)))
    g.add((ACTION, KG.armCode, rdflib.Literal("MARKOWITZ_BASE")))
    g.add((ACTION, KG.decisionDate, _date("2022-02-01")))
    g.add((ACTION, KG.effectiveDate, _date("2022-02-02")))
    g.add((ACTION, KG.status, rdflib.Literal("APPLIED")))
    g.add((ACTION, KG.guardAsset, KG.AAPL))
    g.add((ACTION, KG.guardTicker, rdflib.Literal("AAPL")))
    g.add((ACTION, KG.knowledgeDate, _date("2022-02-02")))
    # Layer 3 action: asset/ticker absent, portfolio-scale weights present.
    g.add((L3_ACTION, RDF.type, KG.GuardAction))
    g.add((L3_ACTION, KG.actionId, _int(2)))
    g.add((L3_ACTION, KG.bookId, _int(1)))
    g.add((L3_ACTION, KG.actionOfBook, BOOK))
    g.add((L3_ACTION, KG.actionAlert, L3_ALERT))
    g.add((L3_ACTION, KG.backtestRunId, _int(1)))
    g.add((L3_ACTION, KG.armCode, rdflib.Literal("MARKOWITZ_BASE")))
    g.add((L3_ACTION, KG.decisionDate, _date("2022-02-02")))
    g.add((L3_ACTION, KG.effectiveDate, _date("2022-02-03")))
    g.add((L3_ACTION, KG.status, rdflib.Literal("APPLIED")))
    g.add((L3_ACTION, KG.weightBefore, _dec("1.0")))
    g.add((L3_ACTION, KG.weightAfter, _dec("0.8")))
    g.add((L3_ACTION, KG.knowledgeDate, _date("2022-02-03")))


def _add_weights(g: rdflib.Graph) -> None:
    # CASH row: no asset, no holding_name, no target weights.
    g.add((WEIGHT, RDF.type, KG.BookWeightDaily))
    g.add((WEIGHT, KG.weightOfBook, BOOK))
    g.add((WEIGHT, KG.bookId, _int(1)))
    g.add((WEIGHT, KG.backtestRunId, _int(1)))
    g.add((WEIGHT, KG.armCode, rdflib.Literal("MARKOWITZ_BASE")))
    g.add((WEIGHT, KG.weightDate, _date("2022-02-03")))
    g.add((WEIGHT, KG.holdingKey, rdflib.Literal("CASH")))
    g.add((WEIGHT, KG.knowledgeDate, _date("2022-02-03")))
    # A second CASH row, for the explicit "no Asset node" case.
    g.add((CASH_WEIGHT, RDF.type, KG.BookWeightDaily))
    g.add((CASH_WEIGHT, KG.weightOfBook, BOOK))
    g.add((CASH_WEIGHT, KG.bookId, _int(1)))
    g.add((CASH_WEIGHT, KG.backtestRunId, _int(1)))
    g.add((CASH_WEIGHT, KG.armCode, rdflib.Literal("MARKOWITZ_BASE")))
    g.add((CASH_WEIGHT, KG.weightDate, _date("2022-02-04")))
    g.add((CASH_WEIGHT, KG.holdingKey, rdflib.Literal("CASH")))
    g.add((CASH_WEIGHT, KG.knowledgeDate, _date("2022-02-04")))


def _add_performance(g: rdflib.Graph) -> None:
    g.add((PERFORMANCE, RDF.type, KG.BookDailyPerformance))
    g.add((PERFORMANCE, KG.performanceOfBook, BOOK))
    g.add((PERFORMANCE, KG.bookId, _int(1)))
    g.add((PERFORMANCE, KG.backtestRunId, _int(1)))
    g.add((PERFORMANCE, KG.armCode, rdflib.Literal("MARKOWITZ_BASE")))
    g.add((PERFORMANCE, KG.windowId, rdflib.Literal("P1")))
    g.add((PERFORMANCE, KG.performanceDate, _date("2022-02-03")))
    g.add((PERFORMANCE, KG.grossReturn, _dec("0.01")))
    g.add((PERFORMANCE, KG.turnover, _dec("0.2")))
    g.add((PERFORMANCE, KG.costReturn, _dec("0.0002")))
    g.add((PERFORMANCE, KG.netReturn, _dec("0.0098")))
    g.add((PERFORMANCE, KG.nav, _dec("1.01")))
    g.add((PERFORMANCE, KG.drawdown, _dec("0.02")))
    g.add((PERFORMANCE, KG.cashWeight, _dec("0.05")))
    g.add((PERFORMANCE, KG.nEquity, _int(30)))
    g.add((PERFORMANCE, KG.knowledgeDate, _date("2022-02-03")))


def _add_summary(g: rdflib.Graph) -> None:
    g.add((SUMMARY, RDF.type, KG.PortfolioPeriodSummary))
    g.add((SUMMARY, KG.summaryOfBook, BOOK))
    g.add((SUMMARY, KG.bookId, _int(1)))
    g.add((SUMMARY, KG.backtestRunId, _int(1)))
    g.add((SUMMARY, KG.armCode, rdflib.Literal("MARKOWITZ_BASE")))
    g.add((SUMMARY, KG.windowId, rdflib.Literal("P1")))
    g.add((SUMMARY, KG.segment, rdflib.Literal("P1")))
    g.add((SUMMARY, KG.dateFrom, _date("2022-01-03")))
    g.add((SUMMARY, KG.dateTo, _date("2022-10-12")))
    g.add((SUMMARY, KG.cumulativeReturn, _dec("0.1")))
    g.add((SUMMARY, KG.annualizedReturn, _dec("0.12")))
    g.add((SUMMARY, KG.annualizedVol, _dec("0.18")))
    g.add((SUMMARY, KG.exPostSharpe, _dec("0.6")))
    g.add((SUMMARY, KG.maxDrawdown, _dec("0.2")))
    g.add((SUMMARY, KG.totalTurnover, _dec("3.0")))
    g.add((SUMMARY, KG.totalCostBps, _dec("300")))
    g.add((SUMMARY, KG.nRebalances, _int(10)))
    g.add((SUMMARY, KG.nGuardActions, _int(5)))
    g.add((SUMMARY, KG.knowledgeDate, _date("2022-10-12")))


def _add_test(g: rdflib.Graph) -> None:
    g.add((TEST, RDF.type, KG.BacktestTest))
    g.add((TEST, KG.backtestRunId, _int(1)))
    g.add((TEST, KG.runLabel, rdflib.Literal("rule")))
    g.add((TEST, KG.windowId, rdflib.Literal("P1")))
    g.add((TEST, KG.segment, rdflib.Literal("P1")))
    g.add((TEST, KG.armA, rdflib.Literal("MARKOWITZ_BASE")))
    g.add((TEST, KG.armB, rdflib.Literal("TOPN_MV_NOGUARD")))
    g.add((TEST, KG.testName, rdflib.Literal("memmel_jk")))
    g.add((TEST, KG.statistic, _dec("1.2")))
    g.add((TEST, KG.pValue, _dec("0.05")))
    g.add((TEST, KG.nObs, _int(100)))
    g.add((TEST, KG.knowledgeDate, _date("2026-11-01")))


def _add_ticker(g: rdflib.Graph) -> None:
    g.add((TICKER, RDF.type, KG.TickerHistory))
    g.add((TICKER, KG.tickerHistoryCik, rdflib.Literal("0000320193")))
    g.add((TICKER, KG.historicalSymbol, rdflib.Literal("AAPL")))
    g.add((TICKER, KG.canonicalSymbol, rdflib.Literal("AAPL")))
    g.add((TICKER, KG.validFrom, _date("2020-01-01")))
    g.add((TICKER, KG.tickerHistoryAsset, KG.AAPL))


def _add_orchestrator(g: rdflib.Graph) -> None:
    g.add((RUN, RDF.type, KG.OrchestratorRun))
    g.add((RUN, KG.orchestratorRunId, _int(1)))
    g.add((RUN, KG.handle, rdflib.Literal("run-1")))
    g.add((RUN, KG.runKind, rdflib.Literal("pipeline")))
    g.add((RUN, KG.runAsOf, _date("2026-11-01")))
    g.add((RUN, KG.surface, rdflib.Literal("cli")))
    g.add((RUN, KG.status, rdflib.Literal("completed")))
    g.add(
        (
            RUN,
            KG.startedAt,
            rdflib.Literal("2026-11-01T00:00:00", datatype=XSD.dateTime),
        )
    )
    g.add((STEP, RDF.type, KG.OrchestratorStep))
    g.add((STEP, KG.stepOfOrchestratorRun, RUN))
    g.add((STEP, KG.handle, rdflib.Literal("run-1")))
    g.add((STEP, KG.ordinal, _int(1)))
    g.add((STEP, KG.stepName, rdflib.Literal("analysis")))
    g.add((STEP, KG.argvJson, rdflib.Literal("[]")))
    g.add((STEP, KG.status, rdflib.Literal("completed")))


def _m018(bundle: rdflib.Dataset) -> rdflib.Graph:
    """One conformant individual of every new class, with every nullable case absent."""
    g = _flat(bundle)
    _add_book(g)
    _add_rebalance(g)
    _add_alerts(g)
    _add_action(g)
    _add_weights(g)
    _add_performance(g)
    _add_summary(g)
    _add_test(g)
    _add_ticker(g)
    _add_orchestrator(g)
    return g


def test_the_whole_m018_set_conforms(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    assert _violations(_m018(bundle), shapes) == set()


def test_an_orchestrator_run_with_only_its_key_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    """The handoff §3.1 has no base-table nullability and the view has 0 rows: only the key is required."""
    g = _flat(bundle)
    g.add((RUN, RDF.type, KG.OrchestratorRun))
    g.add((RUN, KG.orchestratorRunId, _int(1)))
    assert _violations(g, shapes) == set()


def test_an_orchestrator_step_with_only_its_key_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _flat(bundle)
    g.add((RUN, RDF.type, KG.OrchestratorRun))
    g.add((RUN, KG.orchestratorRunId, _int(1)))
    g.add((STEP, RDF.type, KG.OrchestratorStep))
    g.add((STEP, KG.stepOfOrchestratorRun, RUN))
    g.add((STEP, KG.ordinal, _int(1)))
    assert _violations(g, shapes) == set()


@pytest.mark.parametrize(
    ("subject", "path"),
    [
        (BOOK, KG.bookId),
        (REBALANCE, KG.bookId),
        (REBALANCE, KG.executionDate),
        (ALERT, KG.alertState),
        (ACTION, KG.actionAlert),
        (ACTION, KG.bookId),
        (WEIGHT, KG.weightOfBook),
        (PERFORMANCE, KG.nav),
        (SUMMARY, KG.maxDrawdown),
        (TEST, KG.testName),
        (BOOK, KG.runLabel),
        (TEST, KG.runLabel),
        (TICKER, KG.tickerHistoryCik),
        (RUN, KG.orchestratorRunId),
        (STEP, KG.stepOfOrchestratorRun),
        (STEP, KG.ordinal),
    ],
    ids=[
        "book-id",
        "rebalance-book-id",
        "rebalance-date",
        "alert-state",
        "action-alert",
        "action-book-id",
        "weight-book",
        "performance-nav",
        "summary-drawdown",
        "test-name",
        "book-run-label",
        "test-run-label",
        "ticker-cik",
        "run-id",
        "step-run",
        "step-ordinal",
    ],
)
def test_a_missing_required_property_is_caught(
    bundle: rdflib.Dataset,
    shapes: rdflib.Graph,
    subject: rdflib.URIRef,
    path: rdflib.URIRef,
) -> None:
    g = _m018(bundle)
    g.remove((subject, path, None))
    assert _violations(g, shapes) == {(subject, path)}


@pytest.mark.parametrize(
    ("subject", "path", "value"),
    [
        (ALERT, KG.alertState, rdflib.Literal("BOGUS")),
        (ALERT, KG.guardLayer, _int(5)),
        (BOOK, KG.armCode, rdflib.Literal("BOGUS")),
        (TEST, KG.testName, rdflib.Literal("BOGUS")),
        (SUMMARY, KG.segment, rdflib.Literal("BOGUS")),
        (BOOK, KG.excludeHardVetoed, _int(0)),
        (BOOK, KG.runLabel, rdflib.Literal("Rule")),
        (TEST, KG.runLabel, rdflib.Literal("r")),
        (BOOK, KG.windowId, rdflib.Literal("Q1")),
        (TEST, KG.windowId, rdflib.Literal("P1a")),
        (SUMMARY, KG.segment, rdflib.Literal("P2A")),
    ],
    ids=[
        "alert-state",
        "guard-layer",
        "arm-code",
        "test-name",
        "segment",
        "boolean-as-integer",
        "upper-case-label",
        "too-short-label",
        "window-not-p-number",
        "window-with-suffix",
        "segment-upper-case-suffix",
    ],
)
def test_an_invalid_value_is_caught(
    bundle: rdflib.Dataset,
    shapes: rdflib.Graph,
    subject: rdflib.URIRef,
    path: rdflib.URIRef,
    value: rdflib.Literal,
) -> None:
    g = _m018(bundle)
    g.remove((subject, path, None))
    g.add((subject, path, value))
    assert _violations(g, shapes) == {(subject, path)}


@pytest.mark.parametrize(
    ("subject", "path", "value"),
    [
        (BOOK, KG.windowId, rdflib.Literal("P4")),
        (TEST, KG.windowId, rdflib.Literal("P12")),
        (SUMMARY, KG.segment, rdflib.Literal("P2c")),
        (TEST, KG.segment, rdflib.Literal("P12z")),
        (BOOK, KG.runLabel, rdflib.Literal("champ_v1")),
    ],
    ids=["new-window", "two-digit-window", "new-sub-period", "two-digit-sub-period", "family"],
)
def test_a_new_window_sub_period_or_label_conforms(
    bundle: rdflib.Dataset,
    shapes: rdflib.Graph,
    subject: rdflib.URIRef,
    path: rdflib.URIRef,
    value: rdflib.Literal,
) -> None:
    """T-234: the windows and segments are patterns; an unseen P<number> needs no schema edit."""
    g = _m018(bundle)
    g.remove((subject, path, None))
    g.add((subject, path, value))
    assert _violations(g, shapes) == set()


def test_a_layer_one_alert_without_a_value_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _m018(bundle)
    assert (ALERT, KG.alertValue, None) not in g
    assert _violations(g, shapes) == set()


def test_a_layer_three_alert_without_an_asset_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _m018(bundle)
    assert (L3_ALERT, KG.guardAsset, None) not in g
    assert (L3_ALERT, KG.guardTicker, None) not in g
    assert _violations(g, shapes) == set()


def test_a_layer_three_action_without_an_asset_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _m018(bundle)
    assert (L3_ACTION, KG.guardAsset, None) not in g
    assert (L3_ACTION, KG.guardTicker, None) not in g
    assert _violations(g, shapes) == set()


def test_a_cash_weight_without_an_asset_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _m018(bundle)
    assert (CASH_WEIGHT, KG.holdingAsset, None) not in g
    assert (CASH_WEIGHT, KG.holdingName, None) not in g
    assert _violations(g, shapes) == set()


def test_a_cash_weight_with_an_asset_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    """CASH is never an asset (handoff §3.3)."""
    g = _m018(bundle)
    g.add((WEIGHT, KG.holdingAsset, KG.AAPL))
    assert _violations(g, shapes) == {(WEIGHT, None)}


def test_an_equity_weight_with_an_asset_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _m018(bundle)
    g.remove((WEIGHT, KG.holdingKey, None))
    g.add((WEIGHT, KG.holdingKey, rdflib.Literal("AAPL")))
    g.add((WEIGHT, KG.holdingAsset, KG.AAPL))
    assert _violations(g, shapes) == set()


@pytest.mark.parametrize(
    ("subject", "path", "wrong"),
    [
        (REBALANCE, KG.executionDate, _date("2022-01-06")),
        (ALERT, KG.alertDate, _date("2022-02-09")),
        (ACTION, KG.effectiveDate, _date("2022-02-09")),
        (WEIGHT, KG.weightDate, _date("2022-02-09")),
        (PERFORMANCE, KG.performanceDate, _date("2022-02-09")),
        (SUMMARY, KG.dateTo, _date("2022-10-13")),
    ],
    ids=["rebalance", "alert", "action", "weight", "performance", "summary"],
)
def test_a_row_date_that_disagrees_with_knowledge_date_is_caught(
    bundle: rdflib.Dataset,
    shapes: rdflib.Graph,
    subject: rdflib.URIRef,
    path: rdflib.URIRef,
    wrong: rdflib.Literal,
) -> None:
    g = _m018(bundle)
    g.remove((subject, path, None))
    g.add((subject, path, wrong))
    assert _violations(g, shapes) == {(subject, path)}


def test_strategy_book_and_backtest_test_do_not_equate_knowledge_date(
    shapes: rdflib.Graph,
) -> None:
    """Their knowledge_date is the run's created_at day, not a row date (handoff §3.2)."""
    for shape in (KG.StrategyBookShape, KG.BacktestTestShape):
        for prop in shapes.objects(shape, SH.property):
            assert (prop, SH.equals, None) not in shapes


@pytest.mark.parametrize("value", ["0.0", "1.0"], ids=["lower", "upper"])
def test_a_p_value_at_the_bounds_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, value: str
) -> None:
    g = _m018(bundle)
    g.remove((TEST, KG.pValue, None))
    g.add((TEST, KG.pValue, _dec(value)))
    assert _violations(g, shapes) == set()


@pytest.mark.parametrize("value", ["-0.1", "1.2"], ids=["below", "above"])
def test_a_p_value_outside_0_to_1_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph, value: str
) -> None:
    g = _m018(bundle)
    g.remove((TEST, KG.pValue, None))
    g.add((TEST, KG.pValue, _dec(value)))
    assert _violations(g, shapes) == {(TEST, KG.pValue)}


def test_one_observation_conforms(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    g = _m018(bundle)
    g.remove((TEST, KG.nObs, None))
    g.add((TEST, KG.nObs, _int(1)))
    assert _violations(g, shapes) == set()


def test_zero_observations_are_caught(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    g = _m018(bundle)
    g.remove((TEST, KG.nObs, None))
    g.add((TEST, KG.nObs, _int(0)))
    assert _violations(g, shapes) == {(TEST, KG.nObs)}


def test_a_markowitz_base_rebalance_without_a_cycle_run_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _m018(bundle)
    assert (REBALANCE, KG.cycleRunId, None) not in g
    assert _violations(g, shapes) == set()


def test_a_book_without_guard_layers_conforms(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    g = _m018(bundle)
    assert (BOOK, KG.guardLayers, None) not in g
    assert _violations(g, shapes) == set()


def test_an_ordinary_day_weight_without_target_weights_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _m018(bundle)
    assert (WEIGHT, KG.markowitzTargetWeight, None) not in g
    assert (WEIGHT, KG.finalTargetWeight, None) not in g
    assert _violations(g, shapes) == set()


def test_a_book_with_guard_layers_conforms(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    g = _m018(bundle)
    g.add((BOOK, KG.guardLayers, rdflib.Literal("[1, 3, 4]")))
    assert _violations(g, shapes) == set()


def test_a_negative_drawdown_and_cost_conform(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    """No sign convention is stated, so a negative value must not be rejected."""
    g = _m018(bundle)
    g.remove((PERFORMANCE, KG.drawdown, None))
    g.add((PERFORMANCE, KG.drawdown, _dec("-0.1")))
    g.remove((PERFORMANCE, KG.costReturn, None))
    g.add((PERFORMANCE, KG.costReturn, _dec("-0.001")))
    g.remove((SUMMARY, KG.maxDrawdown, None))
    g.add((SUMMARY, KG.maxDrawdown, _dec("-0.2")))
    assert _violations(g, shapes) == set()


def test_a_one_day_ticker_history_conforms(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    """TickerHistory's interval is inclusive: validFrom == validTo is a one-day symbol."""
    g = _m018(bundle)
    g.add((TICKER, KG.validTo, _date("2020-01-01")))  # validFrom is 2020-01-01
    assert _violations(g, shapes) == set()


def test_a_ticker_history_with_valid_to_before_valid_from_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _m018(bundle)
    g.add((TICKER, KG.validTo, _date("2019-01-01")))
    assert _violations(g, shapes) == {(TICKER, KG.validFrom)}


def test_a_ticker_history_with_a_later_valid_to_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _m018(bundle)
    g.add((TICKER, KG.validTo, _date("2021-01-01")))
    assert _violations(g, shapes) == set()


# --- the handoff rule table against rules.ttl ---------------------------------------------------

SELECTION_RULES: dict[str, tuple[str, str | None]] = {
    "LEVERAGE_EXTREME": ("HARD", "3.0"),
    "NEGATIVE_FCF": ("HARD", "0.0"),
    "UTILITY_CASH_COVERAGE": ("HARD", "0.05"),
    "DATA_QUALITY": ("HARD", None),
    "VOLATILITY_SHOCK": ("HARD", None),
    "CRASH_Z_SCORE": ("HARD", None),
    "LIQUIDITY_DISTRESS": ("SOFT", "1.0"),
    "PRICE_CRASH": ("SOFT", "-0.35"),
    "EARNINGS_MISSING": ("SOFT", "400"),
    "BREAK_TREND_200": ("SOFT", None),
}


def _rules() -> rdflib.Graph:
    return rdflib.Graph().parse(SCHEMA / "rules.ttl", format="turtle")


def _selection_rules() -> dict[str, rdflib.term.Node]:
    g = _rules()
    found: dict[str, rdflib.term.Node] = {}
    for rule in g.subjects(RDF.type, KG.RuleDefinition):
        if (rule, KG.validTo, None) in g or str(g.value(rule, KG.category)) == "GUARD":
            continue
        found[str(g.value(rule, KG.ruleId))] = rule
    return found


def _threshold(g: rdflib.Graph, rule: rdflib.term.Node) -> str | None:
    leaf = g.value(rule, KG.hasClause)
    assert isinstance(leaf, rdflib.term.Node)
    # LIQUIDITY_DISTRESS_v11 is the one selection rule with a tree: the handoff's headline
    # threshold is its current-ratio operand (operand1), not the AND root.
    if (leaf, RDF.type, KG.RuleClause) in g:
        leaf = g.value(leaf, KG.operand1)
        assert isinstance(leaf, rdflib.term.Node)
    value = g.value(leaf, KG.thresholdValue)
    return None if value is None else str(value)


def test_the_ten_selection_rules_match_the_handoff_table() -> None:
    g = _rules()
    rules = _selection_rules()
    assert set(rules) == set(SELECTION_RULES)
    for rule_id, (severity, threshold) in SELECTION_RULES.items():
        rule = rules[rule_id]
        assert str(g.value(rule, KG.ruleSeverity)) == severity, rule_id
        assert _threshold(g, rule) == threshold, rule_id


def test_the_new_rule_carries_the_handoff_metric_and_rank() -> None:
    g = _rules()
    rule = _selection_rules()["UTILITY_CASH_COVERAGE"]
    leaf = g.value(rule, KG.hasClause)
    assert str(g.value(leaf, KG.metricName)) == "rule_input.utility_cash_coverage_3y"
    assert str(g.value(leaf, KG.operator)) == "<"
    assert str(g.value(leaf, KG.thresholdValue)) == "0.05"
    assert str(g.value(rule, KG.priorityRank)) == "10"
    valid_from = g.value(rule, KG.validFrom)
    assert isinstance(valid_from, rdflib.Literal)
    assert str(valid_from) == "2026-10-14"
    # T-209 resolves a backtest veto's rule on the run date (2026-10-31), so the
    # definition must still be in force then.
    assert valid_from.toPython() <= date(2026, 10, 31)


def test_the_guard_rules_are_not_in_the_selection_catalog() -> None:
    g = _rules()
    guards = {
        str(g.value(rule, KG.ruleId)): rule
        for rule in g.subjects(RDF.type, KG.RuleDefinition)
        if (rule, KG.validTo, None) not in g and str(g.value(rule, KG.category)) == "GUARD"
    }
    assert set(guards) == {"L1_STOP_LOSS", "L1_REENTRY", "L2_NEWS", "L3_VOL", "L4_DD"}
    for rule in guards.values():
        assert (rule, KG.ruleSeverity, None) not in g
        assert (rule, KG.penaltyPoints, None) not in g
        assert (rule, KG.priorityRank, None) not in g


# --- Work item 26: the backtest selection side --------------------------------------------------

CYCLE = KG.Cycle_test_P1_7
SCHEME = KG.Scheme_test_P1_7
CONFIGURED = KG.Weight_test_P1_7_ScoreTecnico
SNAP = KG.Snap_test_P1_7_1
EFFECTIVE = KG.RankComp_test_P1_7_1_ScoreFinanciero


def _add_selection(g: rdflib.Graph) -> None:
    g.add((CYCLE, RDF.type, KG.SelectionCycle))
    g.add((CYCLE, KG.cycleRunId, _int(7)))
    g.add((CYCLE, KG.cycleType, rdflib.Literal("REPLAY")))
    g.add((CYCLE, KG.runAsOf, _date("2022-01-05")))
    g.add((CYCLE, KG.runId, rdflib.Literal("cycle_run:7")))
    g.add((CYCLE, KG.status, rdflib.Literal("completed")))
    g.add((CYCLE, KG.runLabel, rdflib.Literal("rule")))
    g.add((CYCLE, KG.windowId, rdflib.Literal("P1")))
    g.add((CYCLE, KG.backtestRunId, _int(1)))

    g.add((SCHEME, RDF.type, KG.AttractivenessWeightScheme))
    g.add((SCHEME, KG.schemeId, rdflib.Literal("cycle_run:7")))
    g.add((SCHEME, KG.cycleDate, _date("2022-01-05")))
    g.add((SCHEME, KG.cycleRunId, _int(7)))
    g.add((SCHEME, KG.hasWeightComponent, CONFIGURED))
    g.add((CONFIGURED, RDF.type, KG.WeightComponent))
    g.add((CONFIGURED, KG.weightMetricName, rdflib.Literal("ScoreTecnico")))
    g.add((CONFIGURED, KG.weightValue, _dec("1")))

    g.add((SNAP, RDF.type, KG.AttractivenessSnapshot))
    g.add((SNAP, KG.attractivenessOfAsset, KG.AAPL))
    g.add((SNAP, KG.rankingTicker, rdflib.Literal("AAPL")))
    g.add((SNAP, KG.attractivenessScore, _dec("0.55")))
    g.add(
        (
            SNAP,
            KG.computedAt,
            rdflib.Literal("2022-01-05T18:30:00Z", datatype=XSD.dateTime),
        )
    )
    g.add((SNAP, KG.computedWithScheme, SCHEME))
    g.add((SNAP, KG.rankingOfCycle, CYCLE))
    g.add((SNAP, KG.rankPosition, _int(1)))
    g.add((SNAP, KG.selectedForBook, rdflib.Literal("true", datatype=XSD.boolean)))
    g.add((SNAP, KG.vetoedAtRanking, rdflib.Literal("false", datatype=XSD.boolean)))
    g.add((SNAP, KG.vetoRulesJson, rdflib.Literal("[]")))
    g.add((SNAP, KG.hasEffectiveWeight, EFFECTIVE))
    g.add((EFFECTIVE, RDF.type, KG.WeightComponent))
    g.add((EFFECTIVE, KG.weightMetricName, rdflib.Literal("ScoreFinanciero")))
    g.add((EFFECTIVE, KG.weightValue, _dec("1")))
    g.add((EFFECTIVE, KG.componentValue, _dec("60")))


def test_the_backtest_selection_set_conforms(bundle: rdflib.Dataset, shapes: rdflib.Graph) -> None:
    g = _flat(bundle)
    _add_selection(g)
    assert _violations(g, shapes) == set()


def test_a_ranking_snapshot_with_only_a_ticker_conforms(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _flat(bundle)
    _add_selection(g)
    g.remove((SNAP, KG.attractivenessOfAsset, None))
    assert _violations(g, shapes) == set()


def test_a_ranking_snapshot_without_asset_or_ticker_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _flat(bundle)
    _add_selection(g)
    g.remove((SNAP, KG.attractivenessOfAsset, None))
    g.remove((SNAP, KG.rankingTicker, None))
    assert any(focus == SNAP for focus, _ in _violations(g, shapes))


def test_a_ranking_snapshot_without_a_rank_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _flat(bundle)
    _add_selection(g)
    g.remove((SNAP, KG.rankPosition, None))
    assert _violations(g, shapes) == {(SNAP, KG.rankPosition)}


def test_an_effective_component_without_component_value_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _flat(bundle)
    _add_selection(g)
    g.remove((EFFECTIVE, KG.componentValue, None))
    assert _violations(g, shapes) == {(EFFECTIVE, KG.componentValue)}


def test_a_selection_cycle_with_a_bad_type_is_caught(
    bundle: rdflib.Dataset, shapes: rdflib.Graph
) -> None:
    g = _flat(bundle)
    _add_selection(g)
    g.remove((CYCLE, KG.cycleType, None))
    g.add((CYCLE, KG.cycleType, rdflib.Literal("BOGUS")))
    assert _violations(g, shapes) == {(CYCLE, KG.cycleType)}
