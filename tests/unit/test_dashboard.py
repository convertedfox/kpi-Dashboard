from kpi_dashboard.dashboard import _actual_metric_text, _boolean_metric_display, _status_emoji
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
