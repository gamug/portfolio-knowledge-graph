"""Configuration-keyed backtest metadata for the final delivery (Work item 46, T-851)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import rdflib

from projection.delivery import RunConfig
from projection.run_metadata import RunInfo, build_metadata

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")


def _run(tmp_path: Path, configuration: str) -> tuple[RunInfo, Path]:
    path = tmp_path / f"{configuration}.db"
    path.write_bytes(configuration.encode())
    return (
        RunInfo(
            path=path,
            label="final",
            window="P1",
            date_from="2022-01-03",
            date_to="2022-10-12",
            run_id=1,
            knowledge_date="2026-11-17",
            configuration=configuration,
        ),
        path,
    )


def _config(tmp_path: Path) -> RunConfig:
    return RunConfig(
        path=tmp_path / "config_final.md",
        label="final",
        code_commit="abc1234",
        pr="156",
        results_doc="docs/results.md",
        body="frozen body",
    )


def test_two_configurations_of_one_window_get_two_runs(tmp_path: Path) -> None:
    system, system_path = _run(tmp_path, "SYSTEM_WITH_HIERARCHY")
    control, control_path = _run(tmp_path, "SYSTEM_WITHOUT_HIERARCHY")
    hashes = {
        system_path: hashlib.sha256(system_path.read_bytes()).hexdigest(),
        control_path: hashlib.sha256(control_path.read_bytes()).hexdigest(),
    }
    projection = build_metadata("final", [system, control], hashes, _config(tmp_path))
    graph = rdflib.Graph().parse(data=projection.data, format="turtle")
    system_iri = KG.Run_final_P1_system_with_hierarchy
    control_iri = KG.Run_final_P1_system_without_hierarchy
    assert (system_iri, rdflib.RDF.type, KG.BacktestRun) in graph
    assert (control_iri, rdflib.RDF.type, KG.BacktestRun) in graph
    assert (system_iri, KG.configuration, KG.Configuration_SystemWithHierarchy) in graph
    assert (control_iri, KG.configuration, KG.Configuration_SystemWithoutHierarchy) in graph
    assert len(set(graph.subjects(rdflib.RDF.type, KG.BacktestRun))) == 2
    assert len(set(graph.subjects(rdflib.RDF.type, KG.RunConfiguration))) == 1
