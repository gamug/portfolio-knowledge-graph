"""Veto Hierarchy shapes (Work item 46, T-841-T-846)."""

from __future__ import annotations

from pathlib import Path

import pyshacl
import rdflib
from rdflib.namespace import RDF, RDFS, SH, SKOS, XSD
from rdflib.term import Node

SCHEMA = Path(__file__).resolve().parent.parent / "schema"
KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")

BOOK = KG.Book_T841
ASSET = KG.Asset_T841
CONFIG = KG.Configuration_T841
ALERT_L0 = KG.Alert_T841_L0
ALERT_BLOCKED = KG.Alert_T841_BLOCKED
ACTION = KG.Action_T841
ACTION_BLOCKED = KG.Action_T841_BLOCKED
STOP = KG.Stop_T841
OPTION = KG.Option_T841
SUMMARY = KG.Summary_T841
MEMORY = KG.Memory_T841
PURCHASE = KG.Purchase_T841
CHECK = KG.Check_T841
RULE_L0 = KG.Rule_L0_CARTERA_ACTIVATION
RULE_BLOCKED = KG.Rule_L1_BP_STOP_BLOCKED


def shapes() -> rdflib.Graph:
    return rdflib.Graph().parse(SCHEMA / "shapes.ttl", format="turtle")


def _date(value: str) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.date)


def _decimal(value: str) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.decimal)


def _integer(value: int) -> rdflib.Literal:
    return rdflib.Literal(value, datatype=XSD.integer)


def _base() -> rdflib.Graph:  # noqa: PLR0915
    g = rdflib.Graph()
    g.add((CONFIG, RDF.type, KG.BacktestConfiguration))
    g.add((CONFIG, SKOS.notation, rdflib.Literal("SYSTEM_WITH_HIERARCHY")))
    g.add((CONFIG, RDFS.label, rdflib.Literal("System with hierarchy", lang="en")))
    g.add((CONFIG, RDFS.comment, rdflib.Literal("The System with the hierarchy.", lang="en")))

    g.add((ASSET, RDF.type, KG.Asset))
    g.add((ASSET, KG.tickerSymbol, rdflib.Literal("T841")))
    g.add((ASSET, KG.cikNumber, rdflib.Literal("0000000841")))

    g.add((BOOK, RDF.type, KG.StrategyBook))
    g.add((BOOK, KG.bookId, _integer(3)))
    g.add((BOOK, KG.backtestRunId, _integer(1)))
    g.add((BOOK, KG.runLabel, rdflib.Literal("final")))
    g.add((BOOK, KG.windowId, rdflib.Literal("C1")))
    g.add((BOOK, KG.backtestStartDate, _date("2022-01-03")))
    g.add((BOOK, KG.backtestEndDate, _date("2026-10-15")))
    g.add((BOOK, KG.runStatus, rdflib.Literal("completed")))
    g.add((BOOK, KG.armCode, rdflib.Literal("TOPN_MV_GUARD_NO_NLP")))
    g.add((BOOK, KG.objective, rdflib.Literal("min_var")))
    g.add((BOOK, KG.excludeHardVetoed, rdflib.Literal(False)))
    g.add((BOOK, KG.configuration, CONFIG))
    g.add((BOOK, KG.knowledgeDate, _date("2026-10-15")))

    for rule, rule_id, layer in (
        (RULE_L0, "L0_CARTERA_ACTIVATION", 0),
        (RULE_BLOCKED, "L1_BP_STOP_BLOCKED", 1),
    ):
        g.add((rule, RDF.type, KG.RuleDefinition))
        g.add((rule, KG.ruleId, rdflib.Literal(rule_id)))
        g.add((rule, KG.category, rdflib.Literal("GUARD")))
        g.add((rule, KG.guardLayer, _integer(layer)))
        g.add((rule, KG.validFrom, _date("2019-01-02")))
        clause = KG[f"Pred_{rule_id}"]
        g.add((rule, KG.hasClause, clause))
        g.add((clause, RDF.type, KG.GraphPredicate))
        g.add((clause, KG.predicateName, rdflib.Literal(f"Guard{rule_id}")))

    for alert, rule, layer, state, value, threshold in (
        (ALERT_L0, RULE_L0, 0, "SCALE", "0.81", "0.82"),
        (ALERT_BLOCKED, RULE_BLOCKED, 1, "BLOCKED", None, None),
    ):
        g.add((alert, RDF.type, KG.GuardAlert))
        g.add((alert, KG.alertId, _integer(1 if alert == ALERT_L0 else 2)))
        g.add((alert, KG.backtestRunId, _integer(1)))
        g.add((alert, KG.windowId, rdflib.Literal("C1")))
        g.add((alert, KG.alertDate, _date("2022-04-22")))
        g.add((alert, KG.guardLayer, _integer(layer)))
        g.add((alert, KG.alertRule, rule))
        g.add((alert, KG.alertState, rdflib.Literal(state)))
        g.add((alert, KG.knowledgeDate, _date("2022-04-22")))
        if value is not None:
            g.add((alert, KG.alertValue, _decimal(value)))
        if threshold is not None:
            g.add((alert, KG.alertThreshold, _decimal(threshold)))

    for action, alert, status in (
        (ACTION, ALERT_L0, "APPLIED"),
        (ACTION_BLOCKED, ALERT_BLOCKED, "BLOCKED"),
    ):
        g.add((action, RDF.type, KG.GuardAction))
        g.add((action, KG.actionId, _integer(1 if action == ACTION else 2)))
        g.add((action, KG.bookId, _integer(3)))
        g.add((action, KG.backtestRunId, _integer(1)))
        g.add((action, KG.armCode, rdflib.Literal("TOPN_MV_GUARD_NO_NLP")))
        g.add((action, KG.decisionDate, _date("2022-04-22")))
        g.add((action, KG.effectiveDate, _date("2022-04-25")))
        g.add((action, KG.status, rdflib.Literal(status)))
        g.add((action, KG.actionOfBook, BOOK))
        g.add((action, KG.actionAlert, alert))
        g.add((action, KG.knowledgeDate, _date("2022-04-25")))

    g.add((STOP, RDF.type, KG.StopEvent))
    g.add((STOP, KG.stopOfBook, BOOK))
    g.add((STOP, KG.stopDate, _date("2022-01-05")))
    g.add((STOP, KG.stoppedAsset, ASSET))
    g.add((STOP, KG.stopWeightBefore, _decimal("0.02")))
    g.add((STOP, KG.filterState, rdflib.Literal(True)))
    g.add((STOP, KG.filterDecisionDate, _date("2021-12-31")))
    g.add((STOP, KG.exposureScale, _decimal("1")))
    g.add((STOP, KG.rhoW0, _decimal("0.83")))
    g.add((STOP, KG.rho, _decimal("0.83")))
    g.add((STOP, KG.chooser, rdflib.Literal("rule")))
    g.add((STOP, KG.cashLeft, _decimal("0")))
    g.add((STOP, KG.portfolioCheckPassed, rdflib.Literal(True)))
    g.add((STOP, KG.chosenCash, rdflib.Literal(True)))
    g.add((STOP, KG.knowledgeDate, _date("2022-01-05")))

    g.add((OPTION, RDF.type, KG.DestinationOption))
    g.add((OPTION, KG.optionOfStop, STOP))
    g.add((OPTION, KG.optionAsset, ASSET))
    g.add((OPTION, KG.optionIsSpy, rdflib.Literal(False)))
    g.add((OPTION, KG.optionRho, _decimal("0.84")))
    g.add((OPTION, KG.optionR, _decimal("0.03")))
    g.add((OPTION, KG.optionBeta, _decimal("0.15")))
    g.add((OPTION, KG.optionRank, _integer(407)))
    g.add((OPTION, KG.optionScore, _decimal("45.6")))
    g.add((OPTION, KG.optionSector, _integer(6)))
    g.add((OPTION, KG.optionSizeFraction, _decimal("1")))
    g.add((OPTION, KG.optionWeight, _decimal("0.02")))
    g.add((OPTION, KG.menuPosition, _integer(1)))

    g.add((SUMMARY, RDF.type, KG.StopRejectionSummary))
    g.add((SUMMARY, KG.summaryOfStop, STOP))
    g.add((SUMMARY, KG.rejectedHardVeto, _integer(91)))
    g.add((SUMMARY, KG.rejectedZoneNoSignal, _integer(0)))

    g.add((MEMORY, RDF.type, KG.StopMemory))
    g.add((MEMORY, KG.memoryOfBook, BOOK))
    g.add((MEMORY, KG.memoryAsset, ASSET))
    g.add((MEMORY, KG.memorySince, _date("2022-01-05")))
    g.add((MEMORY, KG.memoryReleasedOn, _date("2022-02-01")))
    g.add((MEMORY, KG.memoryReleaseCause, rdflib.Literal("price")))
    g.add((MEMORY, KG.memoryStartKind, rdflib.Literal("stop")))

    g.add((PURCHASE, RDF.type, KG.ReplacementPurchase))
    g.add((PURCHASE, KG.purchaseOfStop, STOP))
    g.add((PURCHASE, KG.replacementAsset, ASSET))
    g.add((PURCHASE, KG.orderDate, _date("2022-01-05")))
    g.add((PURCHASE, KG.replacementExecutionDate, _date("2022-01-06")))
    g.add((PURCHASE, KG.machineEntrySession, _date("2022-01-05")))
    g.add((PURCHASE, KG.replacementWeight, _decimal("0.02")))
    g.add((PURCHASE, KG.sizeFraction, _decimal("1")))
    g.add((PURCHASE, KG.replacementRank, _integer(407)))
    g.add((PURCHASE, KG.rankBucket, rdflib.Literal(">250")))
    g.add((PURCHASE, KG.filterState, rdflib.Literal(True)))
    g.add((PURCHASE, KG.filterDecisionDate, _date("2021-12-31")))
    g.add((PURCHASE, KG.replacementStoppedBy, STOP))

    g.add((CHECK, RDF.type, KG.ReplacementCheck))
    g.add((CHECK, KG.checkOfPurchase, PURCHASE))
    g.add((CHECK, KG.checkDate, _date("2022-02-01")))
    g.add((CHECK, KG.candidate, rdflib.Literal(True)))
    g.add((CHECK, KG.kept, rdflib.Literal(True)))
    return g


def _validate(data: rdflib.Graph) -> tuple[bool, rdflib.Graph]:
    conforms, results, _ = pyshacl.validate(data, shacl_graph=shapes())
    assert isinstance(results, rdflib.Graph)
    return conforms, results


def _foci(results: rdflib.Graph) -> set[Node]:
    return {focus for focus in results.objects(None, SH.focusNode)}


def test_the_positive_veto_event_fixture_conforms() -> None:
    conforms, results = _validate(_base())
    assert conforms, results.serialize(format="turtle")


def test_a_blocked_alert_with_a_threshold_fails() -> None:
    data = _base()
    data.add((ALERT_BLOCKED, KG.alertThreshold, _decimal("12.5")))
    conforms, results = _validate(data)
    assert not conforms
    assert ALERT_BLOCKED in _foci(results)


def test_a_blocked_alert_with_a_value_fails() -> None:
    data = _base()
    data.add((ALERT_BLOCKED, KG.alertValue, _decimal("12.5")))
    conforms, results = _validate(data)
    assert not conforms
    assert ALERT_BLOCKED in _foci(results)


def test_a_price_like_property_on_a_stop_event_fails() -> None:
    data = _base()
    data.add((STOP, KG.stopDistancePct, _decimal("-16.7")))
    conforms, results = _validate(data)
    assert not conforms
    assert STOP in _foci(results)


def test_c1_is_admitted_by_the_book_and_alert_shapes() -> None:
    data = _base()
    assert _validate(data)[0]
    data.remove((BOOK, KG.windowId, None))
    data.add((BOOK, KG.windowId, rdflib.Literal("C")))
    conforms, results = _validate(data)
    assert not conforms
    assert BOOK in _foci(results)


def test_the_new_shapes_are_declared() -> None:
    g = shapes()
    for name in (
        "BacktestConfigurationShape",
        "DecisionEventShape",
        "FormationTargetShape",
        "RetentionDecisionShape",
        "RetentionHoldShape",
        "RetentionRejectionShape",
        "StopEventShape",
        "DestinationOptionShape",
        "StopRejectionSummaryShape",
        "StopMemoryShape",
        "ReplacementPurchaseShape",
        "ReplacementCheckShape",
        "VetoEventNoPriceShape",
    ):
        assert (KG[name], RDF.type, SH.NodeShape) in g


def test_an_invalid_memory_release_cause_fails() -> None:
    data = _base()
    data.remove((MEMORY, KG.memoryReleaseCause, None))
    data.add((MEMORY, KG.memoryReleaseCause, rdflib.Literal("manual")))
    conforms, results = _validate(data)
    assert not conforms
    assert MEMORY in _foci(results)


def test_a_memory_episode_without_its_start_kind_fails() -> None:
    data = _base()
    data.remove((MEMORY, KG.memoryStartKind, None))
    conforms, results = _validate(data)
    assert not conforms
    assert MEMORY in _foci(results)
