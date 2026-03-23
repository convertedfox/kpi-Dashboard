import pandas as pd

from kpi_dashboard.dashboard import (
    _actual_metric_text,
    _boolean_metric_display,
    _build_grouped_bar_chart_frame,
    _status_emoji,
)
from kpi_dashboard.models import KPIDefinition, KPIRenderType, KPIValueKind


def test_status_emoji_maps_target_status_to_metric_emojis() -> None:
    assert _status_emoji("reached") == "🟢"
    assert _status_emoji("behind") == "🔴"
    assert _status_emoji("missing") == "🟡"


def test_boolean_metric_display_uses_actual_value_semantics() -> None:
    assert _boolean_metric_display(True) == ("🟢", "Ja")
    assert _boolean_metric_display(False) == ("🔴", "Nein")
    assert _boolean_metric_display(None) == ("🟡", "Kein Stand")


def test_actual_metric_text_prefixes_numeric_values_with_status_emoji() -> None:
    kpi = KPIDefinition(
        kpi_id="1.3::matchmaking",
        project_id="1.3",
        project_name="Match making-Consulting",
        group_id="1",
        group_name="Matchmaking, Vermarktung und Vertrieb",
        kpi_name="erfolgreiche Match-Makings",
        unit="Anzahl",
        source="Test",
        frequency="halbjährlich",
        display_hint="Balken-Diagramm",
        render_type=KPIRenderType.BALKEN,
        data_logistics="manuell",
        value_kind=KPIValueKind.NUMBER,
    )

    assert _actual_metric_text(12, "reached", kpi) == "🟢 12"
    assert _actual_metric_text(None, "missing", kpi) == "🟡 Kein Stand"


def test_build_grouped_bar_chart_frame_melts_series_for_side_by_side_bars() -> None:
    frame = pd.DataFrame(
        [
            {"Periode": "2026-H1", "Ist": 3, "Ziel": 5},
            {"Periode": "2026-H2", "Ist": 4, "Ziel": 6},
        ]
    )

    chart_frame = _build_grouped_bar_chart_frame(
        frame,
        category_column="Periode",
        value_columns=["Ist", "Ziel"],
    )

    assert chart_frame.to_dict("records") == [
        {"Periode": "2026-H1", "Serie": "Ist", "Wert": 3},
        {"Periode": "2026-H2", "Serie": "Ist", "Wert": 4},
        {"Periode": "2026-H1", "Serie": "Ziel", "Wert": 5},
        {"Periode": "2026-H2", "Serie": "Ziel", "Wert": 6},
    ]
