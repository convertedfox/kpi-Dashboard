from pathlib import Path

import pytest
from openpyxl import load_workbook

from kpi_dashboard.dashboard import _build_kpi_chart_frame
from kpi_dashboard.models import format_value
from kpi_dashboard.plan_importer import import_plan_matrix
from kpi_dashboard.store import load_dataset

SOURCE = Path("data/imports/2026-11-10_plan_matrix.xlsx")
BASELINE = Path("data/imports/kpis_before_2026-11-10.json")


def test_revised_plan_matrix_imports_all_cells_as_plans(tmp_path: Path) -> None:
    data = tmp_path / "kpis.json"
    data.write_bytes(BASELINE.read_bytes())
    before = load_dataset(data)
    result = import_plan_matrix(data, SOURCE)
    after = load_dataset(data)
    assert (result.target_count, result.milestone_count, result.status_count) == (72, 7, 2)
    assert after.measurements == before.measurements == []
    assert after.projects == before.projects
    assert len(after.kpis) == 36
    assert {m.planned_status for m in after.planned_milestones} == {None, "ja", "in Arbeit"}
    targets = {(t.kpi_id, t.period): t.value for t in after.targets}
    assert targets[("1.3::anzahl-beratung-unternehmen", "2028-H2")] == 45
    assert targets[("3.2::zugriffe-auf-zus-shop", "2026-H2")] == 3000
    assert targets[("3.1::abgeschlossene-curricula", "2031-H2")] == 1600
    assert targets[("3.2::ctr", "2026-H2")] == 0.04
    definitions = {k.kpi_id: k for k in after.kpis}
    ctr = definitions["3.2::ctr"]
    assert format_value(0.04, ctr.value_kind, ctr.unit) == "4 %"
    ratio = definitions["3.1::anteil-beratungsgesprache-mit-modul-o-mat"]
    assert format_value(1, ratio.value_kind, ratio.unit) == "100 %"
    frame = _build_kpi_chart_frame(after, ratio)
    assert frame["Ist"].isna().all()
    assert frame.loc[frame["Periode"] == "2026-H2", "Ziel"].iloc[0] == 50
    retired = {
        "1.2::produktionsreifes-tool",
        "1.2::mvp-mit-validiertem-tool-und-prozess",
        "1.3::erfolgreiche-match-makings",
        "3.2::prozesse-uber-zus-infrastruktur",
        "3.1::beratungsgesprache-mit-modul-o-mat",
    }
    assert not retired.intersection(definitions)
    assert all(t.kpi_id in definitions for t in after.targets)
    assert all(
        t in after.targets
        for t in before.targets
        if t.kpi_id not in retired
        and not t.kpi_id.startswith(
            ("3.1::abgeschlossene", "3.1::besucher", "3.2::buchungen", "3.2::kunden")
        )
    )
    first_bytes = data.read_bytes()
    import_plan_matrix(data, SOURCE)
    assert data.read_bytes() == first_bytes


def test_plan_import_failure_does_not_modify_dataset(tmp_path: Path) -> None:
    data = tmp_path / "kpis.json"
    data.write_bytes(BASELINE.read_bytes())
    workbook = load_workbook(SOURCE)
    workbook["3.2 ZuS Infrastruktur incl Shop"]["B5"] = "unzulässiger Wert"
    source = tmp_path / "invalid.xlsx"
    workbook.save(source)
    with pytest.raises(ValueError):
        import_plan_matrix(data, source)
    assert data.read_bytes() == BASELINE.read_bytes()


def test_plan_import_rejects_duplicate_milestone_period(tmp_path: Path) -> None:
    data = tmp_path / "kpis.json"
    data.write_bytes(BASELINE.read_bytes())
    workbook = load_workbook(SOURCE)
    workbook["1.2 Skill Gap Analyzer"]["A5"] = "2026-H1"
    source = tmp_path / "duplicate.xlsx"
    workbook.save(source)
    with pytest.raises(ValueError, match="doppelter Meilenstein"):
        import_plan_matrix(data, source)
    assert data.read_bytes() == BASELINE.read_bytes()
