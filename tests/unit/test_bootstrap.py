from pathlib import Path

from kpi_dashboard.bootstrap import build_dataset_from_workbook
from kpi_dashboard.models import KPIRenderType, KPIValueKind, format_value

WORKBOOK_PATH = Path("plan/Projektbericht Innovationsprojekte.xlsx")


def test_bootstrap_builds_expected_dataset() -> None:
    dataset = build_dataset_from_workbook(WORKBOOK_PATH)

    assert dataset.portfolio_name == "Projekt-Controlling Innovationsprojekte"
    assert len(dataset.projects) == 20
    assert len(dataset.kpis) == 36
    assert len(dataset.measurements) == 0

    skill_gap_project = next(project for project in dataset.projects if project.project_id == "1.2")
    assert skill_gap_project.project_name == "Skill Gap Analyzer"

    mvp_kpi = next(kpi for kpi in dataset.kpis if kpi.project_id == "1.2" and "MVP" in kpi.kpi_name)
    assert mvp_kpi.value_kind is KPIValueKind.BOOLEAN
    assert mvp_kpi.render_type is KPIRenderType.AMPEL

    production_kpi = next(
        kpi
        for kpi in dataset.kpis
        if kpi.project_id == "1.2" and "Produktionsreifes Tool" in kpi.kpi_name
    )
    assert production_kpi.value_kind is KPIValueKind.BOOLEAN
    assert production_kpi.render_type is KPIRenderType.AMPEL

    process_kpi = next(
        kpi for kpi in dataset.kpis if kpi.project_id == "6.1" and "on Time" in kpi.kpi_name
    )
    assert process_kpi.value_kind is KPIValueKind.PERCENTAGE
    assert process_kpi.render_type is KPIRenderType.FORTSCHRITT

    target = next(
        record
        for record in dataset.targets
        if record.kpi_id == mvp_kpi.kpi_id and record.period == "2026-H2"
    )
    assert target.value is False

    offer_db_kpi = next(
        kpi
        for kpi in dataset.kpis
        if kpi.project_id == "3.4" and "Übernahme Angebotsdaten in DB" in kpi.kpi_name
    )
    offer_db_target = next(
        record
        for record in dataset.targets
        if record.kpi_id == offer_db_kpi.kpi_id and record.period == "2026-H2"
    )
    assert offer_db_target.value == 0.6
    assert (
        format_value(
            offer_db_target.value,
            offer_db_kpi.value_kind,
            offer_db_kpi.unit,
            offer_db_kpi.max_value,
        )
        == "60 %"
    )
