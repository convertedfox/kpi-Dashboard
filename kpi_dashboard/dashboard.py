from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from kpi_dashboard.analytics import (
    available_periods,
    build_group_status_rows,
    build_portfolio_summary,
    evaluate_target_status,
    kpis_for_project,
    measurements_for_kpi,
    projects_for_group,
    target_for_period,
    targets_for_kpi,
)
from kpi_dashboard.models import KPIDefinition, KPIValueKind, format_value, period_sort_key
from kpi_dashboard.store import load_or_bootstrap_dataset

DATA_PATH = Path("data/kpis.json")
WORKBOOK_PATH = Path("plan/Projektbericht Innovationsprojekte.xlsx")


@st.cache_data(show_spinner=False)
def _load_dataset():
    return load_or_bootstrap_dataset(DATA_PATH, WORKBOOK_PATH)


def render_app() -> None:
    st.set_page_config(
        page_title="Innovationsprojekte KPI Dashboard",
        layout="wide",
        page_icon=":material/query_stats:",
    )

    dataset = _load_dataset()
    periods = available_periods(dataset)
    if not periods:
        st.error("Keine Ziel- oder Ist-Stände verfügbar.")
        return

    group_options = {project.group_id: project.group_name for project in dataset.projects}
    sorted_groups = sorted(group_options.items(), key=lambda item: item[1].casefold())

    with st.sidebar:
        st.title("Filter")
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
        st.code(str(DATA_PATH))

    st.title("Innovationsprojekte KPI Dashboard")
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
        st.metric(f"Ist-Stände {summary.selected_year}", summary.measurement_count, border=True)
        st.metric(f"Ziel erreicht {summary.selected_year}", summary.reached_count, border=True)
        st.metric(f"Ohne Ist-Stand {summary.selected_year}", summary.missing_count, border=True)


def _render_group_overview(dataset, period: str, group_filter: str | None) -> None:
    rows = build_group_status_rows(dataset, period, group_filter)
    with st.container(border=True):
        st.subheader(f"Projektstatus nach Gruppen {period}")
        if not rows:
            st.info("Keine Projektdaten verfügbar.")
            return
        frame = pd.DataFrame(rows)
        st.bar_chart(frame, x="Gruppe", y=["Erfasst", "Ziel erreicht"], horizontal=False)
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
        st.markdown(_status_label(selected_status))

        metric_columns = st.columns(2)
        with metric_columns[0]:
            st.metric(
                f"Ist {selected_period}",
                (
                    format_value(selected_actual.value, kpi.value_kind, kpi.unit, kpi.max_value)
                    if selected_actual is not None
                    else "Kein Stand"
                ),
                border=True,
            )
        with metric_columns[1]:
            st.metric(
                f"Ziel {period_sort_key(selected_period)[0]}",
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

        if kpi.value_kind in {KPIValueKind.BOOLEAN, KPIValueKind.ORDINAL}:
            st.bar_chart(chart_frame, x="Periode", y=["Ist", "Ziel"])
        else:
            st.line_chart(chart_frame, x="Periode", y=["Ist", "Ziel"])

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
                "Ist": _numeric_value(actual.value) if actual is not None else None,
                "Ziel": _numeric_value(target.value) if target is not None else None,
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


def _status_label(status: str) -> str:
    labels = {
        "reached": ":green[Ziel erreicht]",
        "behind": ":red[Ziel noch nicht erreicht]",
        "missing": ":gray[Kein Ist-Stand für diese Periode]",
    }
    return labels[status]


def _numeric_value(value: object) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    raise TypeError(f"nicht numerischer KPI-Wert: {value!r}")
