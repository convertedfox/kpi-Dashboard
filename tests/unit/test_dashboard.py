import pandas as pd
from pathlib import Path
from typing import cast

from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import ButtonGroup

from kpi_dashboard.dashboard import (
    _actual_metric_text,
    _boolean_metric_display,
    _build_grouped_bar_chart_frame,
    _build_line_chart_frame,
    _build_milestone_frame,
    _build_kpi_chart_frame,
    _build_progress_ring_frame,
    _status_emoji,
)
from kpi_dashboard.models import KPIDefinition, KPIRenderType, KPIValueKind
from kpi_dashboard.store import load_dataset


def _project_buttons(app: AppTest) -> ButtonGroup:
    return cast(ButtonGroup, app.get("button_group")[0])


def test_project_selection_supports_multiple_projects_and_empty_selection() -> None:
    app = AppTest.from_file("main.py").run()
    assert not app.exception
    assert [item.value for item in app.subheader] == ["1.1 Beratungsprojekt VuV"]
    assert "Projekt" not in [item.label for item in app.selectbox]
    assert not app.dataframe
    next(item for item in app.toggle if item.label == "Tabellenansicht").set_value(True).run()
    assert len(app.dataframe) == 1
    assert app.dataframe[0].value.columns.tolist() == ["Periode", "Ist Anzeige", "Ziel Anzeige"]
    next(item for item in app.toggle if item.label == "Tabellenansicht").set_value(False).run()
    assert not app.dataframe

    _project_buttons(app).set_value(["1.2", "3.1"]).run()
    assert not app.exception
    assert [item.value for item in app.subheader] == [
        "1.2 Skill Gap Analyzer",
        "3.1 Modul-O-Mat 2.0",
    ]
    # Only the milestone plan remains as a table; chart tables are hidden.
    assert len(app.dataframe) == 1
    app.selectbox[1].set_value("2026-H1").run()
    assert _project_buttons(app).value == ["1.2", "3.1"]

    _project_buttons(app).set_value([]).run()
    assert not app.exception
    assert not app.subheader
    assert app.info[0].value == "Wählen Sie oben ein oder mehrere Projekte aus."


def test_group_filter_limits_project_buttons_and_removes_hidden_projects() -> None:
    app = AppTest.from_file("main.py").run()
    _project_buttons(app).set_value(["1.2", "3.1"]).run()
    app.selectbox[0].set_value("Digitalisierung").run()
    assert not app.exception
    assert _project_buttons(app).value == ["3.1"]
    assert all(option.startswith("3.") for option in _project_buttons(app).options)
    assert [item.value for item in app.subheader] == ["3.1 Modul-O-Mat 2.0"]


def test_milestone_and_kpi_tables_show_every_reporting_half_year() -> None:
    dataset = load_dataset(Path("data/kpis.json"))
    periods = [f"{year}-H{half}" for year in range(2026, 2032) for half in (1, 2)]
    milestones = _build_milestone_frame(dataset, "1.2")
    assert milestones["Periode"].tolist() == periods
    missing = milestones.loc[milestones["Periode"] == "2027-H2"].iloc[0]
    assert missing["Meilenstein"] == missing["Geplanter Erreichungsgrad"] == "–"
    assert milestones.iloc[0]["Geplanter Erreichungsgrad"] == "ja"
    assert _build_milestone_frame(dataset, "1.1").empty

    kpi = next(item for item in dataset.kpis if item.project_id == "1.2")
    frame = _build_kpi_chart_frame(dataset, kpi)
    assert frame["Periode"].tolist() == periods
    assert frame["Ist"].isna().all()
    assert frame.loc[frame["Periode"] == "2027-H2", "Ziel"].isna().all()
    assert frame.loc[frame["Periode"] == "2027-H2", "Ziel Anzeige"].iloc[0] == "-"


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


def test_build_line_chart_frame_drops_missing_values() -> None:
    frame = pd.DataFrame(
        [
            {"Periode": "2026-H1", "Ist": None, "Ziel": 50},
            {"Periode": "2026-H2", "Ist": 60, "Ziel": 70},
        ]
    )

    chart_frame = _build_line_chart_frame(
        frame,
        category_column="Periode",
        value_columns=["Ist", "Ziel"],
    )

    assert chart_frame.to_dict("records") == [
        {"Periode": "2026-H2", "Serie": "Ist", "Wert": 60.0},
        {"Periode": "2026-H1", "Serie": "Ziel", "Wert": 50.0},
        {"Periode": "2026-H2", "Serie": "Ziel", "Wert": 70.0},
    ]


def test_build_progress_ring_frame_clamps_values_to_percentage_range() -> None:
    ring_frame = _build_progress_ring_frame(130)

    assert ring_frame.to_dict("records") == [
        {"Segment": "Ist", "Wert": 100.0},
        {"Segment": "Rest", "Wert": 0.0},
    ]
