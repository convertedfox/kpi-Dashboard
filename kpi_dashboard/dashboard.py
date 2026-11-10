from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from kpi_dashboard.analytics import (
    available_periods,
    build_group_status_rows,
    build_portfolio_summary,
    evaluate_boolean_actual_status,
    evaluate_target_status,
    kpis_for_project,
    measurements_for_kpi,
    projects_for_group,
    target_for_period,
    targets_for_kpi,
)
from kpi_dashboard.models import (
    KPIDefinition,
    KPIRenderType,
    KPIValue,
    KPIValueKind,
    format_value,
    normalize_numeric_value,
    period_sort_key,
)
from kpi_dashboard.store import load_or_bootstrap_dataset, load_or_create_demo_dataset

DATA_PATH = Path("data/kpis.json")
DEMO_DATA_PATH = Path("data/kpis_demo.json")
WORKBOOK_PATH = Path("plan/Projektbericht Innovationsprojekte.xlsx")


@st.cache_data(show_spinner=False)
def _load_dataset(use_demo_data: bool):
    if use_demo_data:
        return load_or_create_demo_dataset(DEMO_DATA_PATH, DATA_PATH, WORKBOOK_PATH)
    return load_or_bootstrap_dataset(DATA_PATH, WORKBOOK_PATH)


def render_app() -> None:
    st.set_page_config(
        page_title="Innovationsprojekte DHBW CAS",
        layout="wide",
        page_icon=":material/query_stats:",
    )

    with st.sidebar:
        st.title("Filter")
        use_demo_data = st.toggle(
            "Demomodus",
            value=False,
            help="Verwendet eine separate Demo-JSON mit künstlichen Ist-Werten.",
        )

    dataset = _load_dataset(use_demo_data)
    periods = available_periods(dataset)
    if not periods:
        st.error("Keine Ziel- oder Ist-Stände verfügbar.")
        return

    group_options = {project.group_id: project.group_name for project in dataset.projects}
    sorted_groups = sorted(group_options.items(), key=lambda item: item[1].casefold())

    with st.sidebar:
        selected_group_label = st.selectbox(
            "Projektgruppe",
            options=["Alle Gruppen", *[name for _, name in sorted_groups]],
            index=0,
        )
        selected_group_id = next(
            (group_id for group_id, name in sorted_groups if name == selected_group_label),
            None,
        )

        filtered_projects = projects_for_group(dataset, selected_group_id)
        project_labels = [
            f"{project.project_id} {project.project_name}" for project in filtered_projects
        ]
        selected_project_label = st.selectbox("Projekt", options=project_labels, index=0)
        selected_project = next(
            project
            for project in filtered_projects
            if f"{project.project_id} {project.project_name}" == selected_project_label
        )

        selected_period = st.selectbox("Berichtsperiode", options=periods, index=len(periods) - 1)

        st.caption("Operative Datenquelle")
        st.code(str(DEMO_DATA_PATH if use_demo_data else DATA_PATH))

    st.title("Innovationsprojekte DHBW CAS")
    st.caption("Fokus auf Projekte, Zielwerte und Ist-Stände je KPI.")

    summary = build_portfolio_summary(dataset, selected_group_id, selected_period)
    _render_summary(summary)

    _render_group_overview(dataset, selected_period, selected_group_id)

    st.divider()
    _render_project_detail(dataset, selected_project.project_id, selected_period)


def _render_summary(summary) -> None:
    with st.container(horizontal=True):
        st.metric("Projekte", summary.project_count, border=True)
        st.metric("KPIs", summary.kpi_count, border=True)


def _render_group_overview(dataset, period: str, group_filter: str | None) -> None:
    rows = build_group_status_rows(dataset, period, group_filter)
    with st.container(border=True):
        st.subheader(f"Projektstatus nach Gruppen {period}")
        if not rows:
            st.info("Keine Projektdaten verfügbar.")
            return
        frame = pd.DataFrame(rows)
        _render_grouped_bar_chart(
            frame, category_column="Gruppe", value_columns=["Erfasst", "Ziel erreicht"]
        )
        st.dataframe(
            frame,
            hide_index=True,
            column_config={
                "Erfassungsquote %": st.column_config.NumberColumn(
                    "Erfassungsquote %",
                    format="%.1f %%",
                ),
                "Zielquote %": st.column_config.NumberColumn("Zielquote %", format="%.1f %%"),
            },
        )


def _render_project_detail(dataset, project_id: str, selected_period: str) -> None:
    project = next(project for project in dataset.projects if project.project_id == project_id)
    project_kpis = kpis_for_project(dataset, project_id)
    statuses = [_status_for_kpi(dataset, kpi, selected_period) for kpi in project_kpis]

    st.subheader(f"{project.project_id} {project.project_name}")
    with st.container(horizontal=True):
        st.metric("Projektgruppe", project.group_name, border=True)
        st.metric("KPIs", len(project_kpis), border=True)
        st.metric("Ziel erreicht", sum(status == "reached" for status in statuses), border=True)
        st.metric("Ohne Ist-Stand", sum(status == "missing" for status in statuses), border=True)

    milestones = sorted(
        (item for item in dataset.planned_milestones if item.project_id == project_id),
        key=lambda item: period_sort_key(item.period),
    )
    if milestones:
        st.markdown("**Meilensteinplanung**")
        st.caption("Planangaben aus der Importdatei; keine gemessenen Ist-Stände.")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Periode": item.period,
                        "Meilenstein": item.name,
                        "Geplanter Erreichungsgrad": item.planned_status or "–",
                    }
                    for item in milestones
                ]
            ),
            hide_index=True,
        )

    columns = st.columns(2)
    for index, kpi in enumerate(project_kpis):
        with columns[index % 2]:
            _render_kpi_card(dataset, kpi, selected_period)


def _render_kpi_card(dataset, kpi: KPIDefinition, selected_period: str) -> None:
    selected_actual = next(
        (
            record
            for record in measurements_for_kpi(dataset, kpi.kpi_id)
            if record.period == selected_period
        ),
        None,
    )
    selected_target = target_for_period(dataset, kpi.kpi_id, selected_period)
    selected_status = evaluate_target_status(
        selected_actual.value if selected_actual is not None else None,
        selected_target.value if selected_target is not None else None,
        kpi.value_kind,
    )

    with st.container(border=True):
        st.markdown(f"**{kpi.kpi_name}**")
        st.caption(f"Einheit: {kpi.unit} | Quelle: {kpi.source} | Frequenz: {kpi.frequency}")
        metric_columns = st.columns(2)
        with metric_columns[0]:
            st.metric(
                f"Ist {selected_period}",
                _actual_metric_text(
                    selected_actual.value if selected_actual is not None else None,
                    selected_status,
                    kpi,
                ),
                border=True,
            )
        with metric_columns[1]:
            st.metric(
                f"Ziel {selected_target.period if selected_target is not None else selected_period}",
                (
                    format_value(selected_target.value, kpi.value_kind, kpi.unit, kpi.max_value)
                    if selected_target is not None
                    else "Kein Ziel"
                ),
                border=True,
            )

        chart_frame = _build_kpi_chart_frame(dataset, kpi)
        if chart_frame.empty:
            st.info("Für diese KPI sind weder Ziel- noch Ist-Stände vorhanden.")
            return

        if kpi.render_type is KPIRenderType.AMPEL:
            pass
        elif kpi.render_type in {KPIRenderType.BALKEN, KPIRenderType.STATUS_SKALA}:
            _render_series_line_chart(
                chart_frame, category_column="Periode", value_columns=["Ist", "Ziel"]
            )
        elif kpi.render_type is KPIRenderType.FORTSCHRITT:
            _render_progress_view(
                chart_frame,
                selected_actual=selected_actual.value if selected_actual is not None else None,
            )
        else:
            _render_series_line_chart(
                chart_frame, category_column="Periode", value_columns=["Ist", "Ziel"]
            )

        st.dataframe(
            chart_frame[["Periode", "Ist Anzeige", "Ziel Anzeige"]],
            hide_index=True,
            column_config={"Ist Anzeige": "Ist", "Ziel Anzeige": "Ziel"},
        )


def _build_kpi_chart_frame(dataset, kpi: KPIDefinition) -> pd.DataFrame:
    actual_by_period = {
        record.period: record for record in measurements_for_kpi(dataset, kpi.kpi_id)
    }
    target_by_period = {record.period: record for record in targets_for_kpi(dataset, kpi.kpi_id)}
    periods = sorted({*actual_by_period, *target_by_period}, key=period_sort_key)

    rows = []
    for period in periods:
        actual = actual_by_period.get(period)
        target = target_by_period.get(period)
        rows.append(
            {
                "Periode": period,
                "Ist": (
                    _numeric_value(actual.value, kpi.value_kind) if actual is not None else None
                ),
                "Ziel": (
                    _numeric_value(target.value, kpi.value_kind) if target is not None else None
                ),
                "Ist Anzeige": (
                    format_value(actual.value, kpi.value_kind, kpi.unit, kpi.max_value)
                    if actual is not None
                    else "-"
                ),
                "Ziel Anzeige": (
                    format_value(target.value, kpi.value_kind, kpi.unit, kpi.max_value)
                    if target is not None
                    else "-"
                ),
            }
        )
    return pd.DataFrame(rows)


def _render_grouped_bar_chart(
    frame: pd.DataFrame,
    *,
    category_column: str,
    value_columns: list[str],
) -> None:
    chart_data = _build_grouped_bar_chart_frame(
        frame,
        category_column=category_column,
        value_columns=value_columns,
    )
    if chart_data.empty:
        st.info("Für diese Ansicht sind keine Werte vorhanden.")
        return

    chart = (
        alt.Chart(chart_data)
        .mark_bar()
        .encode(
            x=alt.X(f"{category_column}:N", sort=None, title=None),
            xOffset=alt.XOffset("Serie:N", sort=value_columns),
            y=alt.Y("Wert:Q", title=None),
            color=alt.Color("Serie:N", sort=value_columns, title=None),
            tooltip=[
                alt.Tooltip(f"{category_column}:N", title=category_column),
                alt.Tooltip("Serie:N", title="Serie"),
                alt.Tooltip("Wert:Q", title="Wert"),
            ],
        )
    )
    st.altair_chart(chart, use_container_width=True)


def _build_grouped_bar_chart_frame(
    frame: pd.DataFrame,
    *,
    category_column: str,
    value_columns: list[str],
) -> pd.DataFrame:
    chart_data = frame[[category_column, *value_columns]].melt(
        id_vars=category_column,
        value_vars=value_columns,
        var_name="Serie",
        value_name="Wert",
    )
    return chart_data.dropna(subset=["Wert"])


def _build_line_chart_frame(
    frame: pd.DataFrame,
    *,
    category_column: str,
    value_columns: list[str],
) -> pd.DataFrame:
    chart_data = frame[[category_column, *value_columns]].melt(
        id_vars=category_column,
        value_vars=value_columns,
        var_name="Serie",
        value_name="Wert",
    )
    return chart_data.dropna(subset=["Wert"])


def _status_for_kpi(dataset, kpi: KPIDefinition, selected_period: str) -> str:
    actual = next(
        (
            record.value
            for record in measurements_for_kpi(dataset, kpi.kpi_id)
            if record.period == selected_period
        ),
        None,
    )
    target = target_for_period(dataset, kpi.kpi_id, selected_period)
    return evaluate_target_status(
        actual, target.value if target is not None else None, kpi.value_kind
    )


def _actual_metric_text(actual: KPIValue | None, status: str, kpi: KPIDefinition) -> str:
    if kpi.render_type is KPIRenderType.AMPEL:
        emoji, text = _boolean_metric_display(actual)
        return f"{emoji} {text}"

    value_text = (
        format_value(actual, kpi.value_kind, kpi.unit, kpi.max_value)
        if actual is not None
        else "Kein Stand"
    )
    return f"{_status_emoji(status)} {value_text}"


def _status_emoji(status: str) -> str:
    emojis = {
        "reached": "🟢",
        "behind": "🔴",
        "missing": "🟡",
    }
    return emojis[status]


def _boolean_metric_display(actual: object | None) -> tuple[str, str]:
    status = evaluate_boolean_actual_status(actual if isinstance(actual, bool) else None)
    labels = {
        "positive": ("🟢", "Ja"),
        "negative": ("🔴", "Nein"),
        "missing": ("🟡", "Kein Stand"),
    }
    return labels[status]


def _render_progress_view(
    chart_frame: pd.DataFrame,
    *,
    selected_actual: KPIValue | None,
) -> None:
    st.caption("Fortschritt der gewählten Berichtsperiode")
    actual_value = (
        _numeric_value(selected_actual, KPIValueKind.PERCENTAGE)
        if selected_actual is not None
        else None
    )

    if actual_value is None:
        st.info("Kein Ist-Stand für diese Periode.")
    else:
        st.altair_chart(_build_progress_ring_chart(actual_value), use_container_width=True)

    st.caption("Verlauf über die Berichtsperioden")
    _render_series_line_chart(
        chart_frame,
        category_column="Periode",
        value_columns=["Ist", "Ziel"],
        y_title="Prozent",
        y_domain=[0, 100],
    )


def _build_progress_ring_frame(actual_value: float) -> pd.DataFrame:
    clamped_value = max(0.0, min(actual_value, 100.0))
    return pd.DataFrame(
        [
            {"Segment": "Ist", "Wert": clamped_value},
            {"Segment": "Rest", "Wert": 100.0 - clamped_value},
        ]
    )


def _build_progress_ring_chart(actual_value: float) -> alt.LayerChart:
    ring_frame = _build_progress_ring_frame(actual_value)
    label_frame = pd.DataFrame([{"Label": f"{actual_value:.0f} %"}])

    ring = (
        alt.Chart(ring_frame)
        .mark_arc(innerRadius=55, cornerRadius=6)
        .encode(
            theta=alt.Theta("Wert:Q"),
            color=alt.Color(
                "Segment:N",
                scale=alt.Scale(domain=["Ist", "Rest"], range=["#0F766E", "#E5E7EB"]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("Segment:N", title="Segment"),
                alt.Tooltip("Wert:Q", title="Wert"),
            ],
        )
    )
    label = alt.Chart(label_frame).mark_text(fontSize=24, fontWeight="bold").encode(text="Label:N")
    return alt.layer(ring, label).properties(height=220)


def _render_series_line_chart(
    frame: pd.DataFrame,
    *,
    category_column: str,
    value_columns: list[str],
    y_title: str | None = None,
    y_domain: list[float] | None = None,
) -> None:
    chart_data = _build_line_chart_frame(
        frame,
        category_column=category_column,
        value_columns=value_columns,
    )
    if chart_data.empty:
        st.info("Für diese Ansicht sind keine Werte vorhanden.")
        return

    y_encoding = alt.Y("Wert:Q", title=y_title)
    if y_domain is not None:
        y_encoding = alt.Y("Wert:Q", title=y_title, scale=alt.Scale(domain=y_domain))

    chart = (
        alt.Chart(chart_data)
        .mark_line(point=True)
        .encode(
            x=alt.X(f"{category_column}:N", sort=None, title=None),
            y=y_encoding,
            color=alt.Color("Serie:N", sort=value_columns, title=None),
            strokeDash=alt.StrokeDash("Serie:N", sort=value_columns, title=None),
            tooltip=[
                alt.Tooltip(f"{category_column}:N", title=category_column),
                alt.Tooltip("Serie:N", title="Serie"),
                alt.Tooltip("Wert:Q", title="Wert", format=".1f"),
            ],
        )
    )
    st.altair_chart(chart, use_container_width=True)


def _progress_fraction(value: object | None) -> float | None:
    if value is None:
        return None
    numeric_value = _numeric_value(value, KPIValueKind.PERCENTAGE)
    return max(0.0, min(numeric_value / 100.0, 1.0))


def _numeric_value(value: object, kind: KPIValueKind) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return normalize_numeric_value(value, kind)
    raise TypeError(f"nicht numerischer KPI-Wert: {value!r}")
