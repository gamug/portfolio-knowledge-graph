"""The live day's news rows, news actions and SPY series (Work item 50).

The final delivery loads these three streams with their own loaders (``news.py``, ``agents.py``
and ``series.py``) into append-only graphs. The live day replaces them every day beside its three
SYSTEM_LIVE graphs, so this module only adapts the live folder to those projectors:

* ``news_rows_file`` (block D ``news_rows.jsonl``) -> :func:`projection.news.parse_rows`,
  :func:`projection.news.link_assets` and the same ``:NewsItem`` triples, in one fixed graph;
* ``news_actions_file`` (the news GUARD's ``news.json``, already in every live export) ->
  :func:`projection.agents._project_news` with the ``SYSTEM_LIVE`` configuration: the actions,
  their evidence linked to each ``:NewsItem``, and the B/C/D levels of each decision date. It is
  projected only when the day brings its news rows, because every evidence row must resolve;
* ``spy_series_file`` (block E ``spy_daily.csv`` restricted to the ``LIVE`` window) -> the same
  ``:DailySeriesPoint`` triples as the final SPY graph.

A day without these files gets three empty graphs, which the loader's swap empties in the store.
Nothing here contacts a store.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

import rdflib
from rdflib.namespace import RDF, XSD

from projection import agents as agent_records
from projection import news as news_records
from projection import series as series_records
from projection.backtest import AssetInfo, GraphBuilder
from projection.live_manifest import (
    LIVE_LABEL,
    LIVE_WINDOW,
    LiveManifest,
    news_actions_graph_name,
    news_graph_name,
    spy_graph_name,
)
from projection.load_veto import VetoGraph

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")

#: The graph kinds this module adds to the live day's three SYSTEM_LIVE kinds.
NEWS_KIND = "news"
NEWS_ACTIONS_KIND = "news_actions"
SPY_KIND = "spy"


class LiveExtrasError(ValueError):
    """A live news/SPY file cannot be accepted; nothing is written."""


@dataclass(frozen=True)
class LiveExtras:
    """The three projected graphs (always three, possibly empty) and what they hold."""

    news: VetoGraph
    news_actions: VetoGraph
    spy: VetoGraph
    news_rows: int
    unresolved_rows: int
    actions: int
    decision_dates: int
    spy_points: int

    @property
    def graphs(self) -> tuple[VetoGraph, VetoGraph, VetoGraph]:
        return (self.news, self.news_actions, self.spy)


def build_extras(
    live: LiveManifest,
    assets: Mapping[str, AssetInfo],
    performance_dates: Sequence[datetime.date],
) -> LiveExtras:
    """Project the day's optional news/SPY files; an absent file gives an empty graph."""
    rows: tuple[news_records.NewsRow, ...] = ()
    news = _empty(news_graph_name(), NEWS_KIND)
    actions = _empty(news_actions_graph_name(), NEWS_ACTIONS_KIND)
    action_count = 0
    decision_dates = 0
    if live.news_rows is not None:
        try:
            parsed = news_records.parse_rows(live.news_rows)
        except news_records.NewsError as exc:
            raise LiveExtrasError(str(exc)) from exc
        rows = news_records.link_assets(parsed, assets)
        news = _news_graph(rows)
        actions, action_count, decision_dates = _news_actions_graph(live, rows)
    spy, spy_points = _spy_graph(live, performance_dates)
    return LiveExtras(
        news=news,
        news_actions=actions,
        spy=spy,
        news_rows=len(rows),
        unresolved_rows=sum(1 for row in rows if row.asset is None),
        actions=action_count,
        decision_dates=decision_dates,
        spy_points=spy_points,
    )


def _empty(graph: str, kind: str) -> VetoGraph:
    return VetoGraph(graph, b"", 0, kind, None, LIVE_WINDOW)


def _veto_graph(graph: str, builder: GraphBuilder, kind: str) -> VetoGraph:
    return VetoGraph(graph, builder.turtle(), len(builder), kind, None, LIVE_WINDOW)


def _news_graph(rows: Sequence[news_records.NewsRow]) -> VetoGraph:
    builder = GraphBuilder()
    for row in rows:
        news_records._add_row(builder, row)
    if len(builder) > news_records.MAX_GRAPH_TRIPLES:
        raise LiveExtrasError(
            f"{news_graph_name()}: {len(builder)} triples exceed the "
            f"{news_records.MAX_GRAPH_TRIPLES}-triple bound of one news graph"
        )
    return _veto_graph(news_graph_name(), builder, NEWS_KIND)


def _news_index(
    rows: Sequence[news_records.NewsRow],
) -> dict[tuple[str, str], news_records.NewsRow]:
    """``(item_id, ticker)`` -> row, refusing a key that maps to two item kinds (as the final)."""
    index: dict[tuple[str, str], news_records.NewsRow] = {}
    kinds: dict[tuple[str, str], str] = {}
    for row in rows:
        key = (row.item_id, row.ticker)
        prior = kinds.setdefault(key, row.item_kind)
        if prior != row.item_kind:
            raise LiveExtrasError(
                f"news rows: ({key[0]}, {key[1]}) maps to both {prior!r} and {row.item_kind!r}; "
                "the :NewsItem IRI is ambiguous"
            )
        index[key] = row
    return index


def _news_actions_graph(
    live: LiveManifest, rows: Sequence[news_records.NewsRow]
) -> tuple[VetoGraph, int, int]:
    path = live.files["news_actions_file"]
    try:
        news = agent_records._news(path)
        stops, sector = agent_records._stops_and_sector_rejections(live.files["jsonl_file"])
    except agent_records.AgentsError as exc:
        raise LiveExtrasError(str(exc)) from exc
    index = _news_index(rows)
    used: dict[tuple[str, str], news_records.NewsRow] = {}
    missing: set[tuple[str, str]] = set()
    for action in news.actions:
        for item in action["test_rows"]:
            key = (str(item[0]), str(item[1]))
            if key in index:
                used[key] = index[key]
            else:
                missing.add(key)
    if missing:
        listing = ", ".join(f"{item_id}:{ticker}" for item_id, ticker in sorted(missing))
        raise LiveExtrasError(
            f"{path}: test rows without a news_rows.jsonl row: {listing} "
            "(every row the news actions cite must be in the day's news rows)"
        )
    bull = agent_records.BullData(raw={}, decisions=())
    data = agent_records.WindowData(
        window=LIVE_WINDOW,
        manager_calls=(),
        narrator_texts=(),
        news=news,
        news_items=used,
        bull=bull,
        counts=agent_records._counts(news, (), (), bull, sector),
        hashes={"news_actions": live.hashes[path]},
        run={"news_actions_file": path.name},
        stops=stops,
    )
    try:
        builder = agent_records._project_news(
            data, LIVE_LABEL, configuration=KG.Configuration_SystemLive
        )
    except agent_records.AgentsError as exc:
        raise LiveExtrasError(str(exc)) from exc
    graph = _veto_graph(news_actions_graph_name(), builder, NEWS_ACTIONS_KIND)
    return graph, len(news.actions), len(news.dates)


def _spy_graph(
    live: LiveManifest, performance_dates: Sequence[datetime.date]
) -> tuple[VetoGraph, int]:
    if live.spy_series is None:
        return _empty(spy_graph_name(), SPY_KIND), 0
    path = live.spy_series
    try:
        raw_rows = series_records._rows(path, series_records.SPY_HEADER)
        points: list[tuple[datetime.date, Decimal, Decimal]] = []
        seen: set[datetime.date] = set()
        for number, row in enumerate(raw_rows, 2):
            where = f"{path}:{number}"
            if row["window"] != LIVE_WINDOW:
                raise LiveExtrasError(f"{where}: window {row['window']!r} is not {LIVE_WINDOW!r}")
            day = series_records._date(row["date"], f"{where}.date")
            if day in seen:
                raise LiveExtrasError(f"{path}: duplicate date {day.isoformat()}")
            seen.add(day)
            points.append(
                (
                    day,
                    series_records._decimal(
                        row["daily_total_return"], f"{where}.daily_total_return"
                    ),
                    series_records._decimal(row["value"], f"{where}.value"),
                )
            )
    except series_records.SeriesError as exc:
        raise LiveExtrasError(str(exc)) from exc
    dates = sorted(seen)
    formation = datetime.date.fromisoformat(live.formation)
    day = datetime.date.fromisoformat(live.day)
    if dates[0] != formation or dates[-1] != day:
        raise LiveExtrasError(
            f"{path}: the series runs {dates[0]}..{dates[-1]}; it must run from the formation "
            f"{formation} to the day {day}"
        )
    book = set(performance_dates)
    if book and book != seen:
        only_spy = sorted(seen - book)[:5]
        only_book = sorted(book - seen)[:5]
        raise LiveExtrasError(
            f"{path}: SPY dates differ from the book's :performanceDate sessions "
            f"(only in SPY: {[str(d) for d in only_spy]}, only in the book: "
            f"{[str(d) for d in only_book]})"
        )
    builder = GraphBuilder()
    for point_day, daily_return, value in points:
        point = series_records.daily_point_iri(
            LIVE_LABEL, series_records.SPY_SLUG, LIVE_WINDOW, point_day
        )
        builder.add(point, RDF.type, KG.DailySeriesPoint)
        builder.add(point, KG.seriesOfConfiguration, KG.Configuration_SPY)
        builder.add(point, KG.windowId, rdflib.Literal(LIVE_WINDOW))
        builder.add(point, KG.seriesDate, rdflib.Literal(point_day.isoformat(), datatype=XSD.date))
        builder.add(
            point,
            KG.dailyTotalReturn,
            rdflib.Literal(format(daily_return, "f"), datatype=XSD.decimal),
        )
        builder.add(point, KG.seriesValue, rdflib.Literal(format(value, "f"), datatype=XSD.decimal))
    return _veto_graph(spy_graph_name(), builder, SPY_KIND), len(points)


def performance_dates(graph: VetoGraph) -> tuple[datetime.date, ...]:
    """The ``:performanceDate`` sessions of the projected SYSTEM_LIVE m018 graph."""
    parsed = rdflib.Graph().parse(data=graph.data, format="turtle")
    dates = {
        datetime.date.fromisoformat(str(value))
        for value in parsed.objects(None, KG.performanceDate)
    }
    return tuple(sorted(dates))
