from pathlib import Path

from kpi_dashboard.analytics import (
    build_coverage_rows,
    build_group_status_rows,
    build_portfolio_summary,
    evaluate_boolean_actual_status,
    evaluate_target_status,
)
from kpi_dashboard.bootstrap import build_dataset_from_workbook
from kpi_dashboard.models import KPIValueKind, MeasurementRecord

WORKBOOK_PATH = Path("plan/Projektbericht Innovationsprojekte.xlsx")


def test_portfolio_summary_for_group_one_uses_expected_totals() -> None:
    dataset = build_dataset_from_workbook(WORKBOOK_PATH)

    summary = build_portfolio_summary(dataset, "1", "2026-H2")

    assert summary.selected_year == 2026
    assert summary.project_count == 4
    assert summary.kpi_count == 8
    assert summary.measurement_count == 0
    assert summary.reached_count == 0
    assert summary.missing_count == 8


def test_group_rows_and_coverage_rows_are_built_for_period() -> None:
    dataset = build_dataset_from_workbook(WORKBOOK_PATH)
    enriched_dataset = dataset.model_copy(
        update={
            "measurements": [
                MeasurementRecord(
                    kpi_id="1.1::roadmap-zur-umsetzung-des-hubs",
                    period="2026-H2",
                    value=True,
                ),
                MeasurementRecord(
                    kpi_id="1.2::mvp-mit-validiertem-tool-und-prozess",
                    period="2026-H2",
                    value=False,
                ),
            ]
        }
    )

    group_rows = build_group_status_rows(enriched_dataset, "2026-H2", None)
    coverage_rows = build_coverage_rows(enriched_dataset, "2026-H2", "1")

    assert any(row["Gruppe"] == "Matchmaking, Vermarktung und Vertrieb" for row in group_rows)
    matchmaking_row = next(
        row for row in group_rows if row["Gruppe"] == "Matchmaking, Vermarktung und Vertrieb"
    )
    assert matchmaking_row["Erfasst"] == 2
    assert matchmaking_row["Ziel erreicht"] == 2
    assert coverage_rows == [
        {
            "Gruppe": "Matchmaking, Vermarktung und Vertrieb",
            "Erfasste KPIs": 2,
            "KPIs Gesamt": 8,
            "Abdeckung %": 25.0,
        }
    ]


def test_evaluate_target_status_uses_exact_goal_logic() -> None:
    assert evaluate_target_status(True, True, KPIValueKind.BOOLEAN) == "reached"
    assert evaluate_target_status(False, True, KPIValueKind.BOOLEAN) == "behind"
    assert evaluate_target_status(9, 10, KPIValueKind.NUMBER) == "behind"
    assert evaluate_target_status(10, 10, KPIValueKind.NUMBER) == "reached"


def test_evaluate_boolean_actual_status_uses_ampel_logic() -> None:
    assert evaluate_boolean_actual_status(True) == "positive"
    assert evaluate_boolean_actual_status(False) == "negative"
    assert evaluate_boolean_actual_status(None) == "missing"
