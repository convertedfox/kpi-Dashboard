from __future__ import annotations

from dataclasses import dataclass

from kpi_dashboard.models import (
    KPIDataset,
    KPIDefinition,
    KPIValue,
    KPIValueKind,
    MeasurementRecord,
    TargetRecord,
    period_sort_key,
)


@dataclass(frozen=True)
class PortfolioSummary:
    selected_year: int
    project_count: int
    kpi_count: int
    measurement_count: int
    reached_count: int
    missing_count: int


def available_periods(dataset: KPIDataset) -> list[str]:
    periods = {measurement.period for measurement in dataset.measurements}
    periods.update(target.period for target in dataset.targets)
    return sorted(periods, key=period_sort_key)


def projects_for_group(dataset: KPIDataset, group_id: str | None) -> list:
    if group_id is None:
        return sorted(dataset.projects, key=lambda project: project.project_id)
    return sorted(
        [project for project in dataset.projects if project.group_id == group_id],
        key=lambda project: project.project_id,
    )


def kpis_for_project(dataset: KPIDataset, project_id: str) -> list[KPIDefinition]:
    return sorted(
        [kpi for kpi in dataset.kpis if kpi.project_id == project_id],
        key=lambda kpi: kpi.kpi_name.casefold(),
    )


def measurements_for_kpi(dataset: KPIDataset, kpi_id: str) -> list[MeasurementRecord]:
    return sorted(
        [measurement for measurement in dataset.measurements if measurement.kpi_id == kpi_id],
        key=lambda measurement: period_sort_key(measurement.period),
    )


def targets_for_kpi(dataset: KPIDataset, kpi_id: str) -> list[TargetRecord]:
    return sorted(
        [target for target in dataset.targets if target.kpi_id == kpi_id],
        key=lambda target: period_sort_key(target.period),
    )


def target_for_period(dataset: KPIDataset, kpi_id: str, period: str) -> TargetRecord | None:
    exact_match = next(
        (
            target
            for target in dataset.targets
            if target.kpi_id == kpi_id and target.period == period
        ),
        None,
    )
    if exact_match is not None:
        return exact_match

    selected_year = period_sort_key(period)[0]
    return next(
        (
            target
            for target in dataset.targets
            if target.kpi_id == kpi_id and target.period == f"{selected_year}-H2"
        ),
        None,
    )


def evaluate_target_status(
    actual: KPIValue | None,
    target: KPIValue | None,
    value_kind: KPIValueKind,
) -> str:
    if actual is None or target is None:
        return "missing"
    if value_kind is KPIValueKind.BOOLEAN:
        return "reached" if bool(actual) is bool(target) else "behind"
    return "reached" if float(actual) >= float(target) else "behind"


def evaluate_boolean_actual_status(actual: KPIValue | None) -> str:
    if actual is None:
        return "missing"
    return "positive" if bool(actual) else "negative"


def build_portfolio_summary(
    dataset: KPIDataset, group_id: str | None, period: str
) -> PortfolioSummary:
    selected_year = period_sort_key(period)[0]
    selected_projects = projects_for_group(dataset, group_id)
    project_ids = {project.project_id for project in selected_projects}
    selected_kpis = [kpi for kpi in dataset.kpis if kpi.project_id in project_ids]

    measurement_count = 0
    reached_count = 0
    for kpi in selected_kpis:
        actual = next(
            (
                measurement.value
                for measurement in dataset.measurements
                if measurement.kpi_id == kpi.kpi_id and measurement.period == period
            ),
            None,
        )
        if actual is not None:
            measurement_count += 1
        target = target_for_period(dataset, kpi.kpi_id, period)
        status = evaluate_target_status(
            actual, target.value if target is not None else None, kpi.value_kind
        )
        if status == "reached":
            reached_count += 1

    return PortfolioSummary(
        selected_year=selected_year,
        project_count=len(selected_projects),
        kpi_count=len(selected_kpis),
        measurement_count=measurement_count,
        reached_count=reached_count,
        missing_count=len(selected_kpis) - measurement_count,
    )


def build_group_status_rows(
    dataset: KPIDataset, period: str, group_filter: str | None
) -> list[dict[str, float | int | str]]:
    grouped: dict[str, dict[str, float | int | str]] = {}
    kpis_by_id = {kpi.kpi_id: kpi for kpi in dataset.kpis}

    for project in dataset.projects:
        if group_filter is not None and project.group_id != group_filter:
            continue
        row = grouped.setdefault(
            project.group_id,
            {
                "Gruppe": project.group_name,
                "Projekte": 0,
                "KPIs": 0,
                "Erfasst": 0,
                "Ziel erreicht": 0,
            },
        )
        row["Projekte"] = int(row["Projekte"]) + 1

    for kpi in dataset.kpis:
        if group_filter is not None and kpi.group_id != group_filter:
            continue
        row = grouped.setdefault(
            kpi.group_id,
            {"Gruppe": kpi.group_name, "Projekte": 0, "KPIs": 0, "Erfasst": 0, "Ziel erreicht": 0},
        )
        row["KPIs"] = int(row["KPIs"]) + 1

    for measurement in dataset.measurements:
        if measurement.period != period:
            continue
        kpi_definition = kpis_by_id.get(measurement.kpi_id)
        if kpi_definition is None:
            continue
        if group_filter is not None and kpi_definition.group_id != group_filter:
            continue
        row = grouped[kpi_definition.group_id]
        row["Erfasst"] = int(row["Erfasst"]) + 1
        target = target_for_period(dataset, kpi_definition.kpi_id, period)
        status = evaluate_target_status(
            measurement.value,
            target.value if target is not None else None,
            kpi_definition.value_kind,
        )
        if status == "reached":
            row["Ziel erreicht"] = int(row["Ziel erreicht"]) + 1

    rows: list[dict[str, float | int | str]] = []
    for row in grouped.values():
        measured = int(row["Erfasst"])
        total = int(row["KPIs"])
        reached = int(row["Ziel erreicht"])
        row["Erfassungsquote %"] = round((measured / total) * 100, 1) if total else 0.0
        row["Zielquote %"] = round((reached / measured) * 100, 1) if measured else 0.0
        rows.append(row)
    return sorted(rows, key=lambda row: str(row["Gruppe"]).casefold())


def build_coverage_rows(
    dataset: KPIDataset, period: str, group_filter: str | None
) -> list[dict[str, float | int | str]]:
    grouped_kpis: dict[str, tuple[str, set[str]]] = {}
    for kpi in dataset.kpis:
        if group_filter is not None and kpi.group_id != group_filter:
            continue
        group_name, kpi_ids = grouped_kpis.setdefault(kpi.group_id, (kpi.group_name, set()))
        kpi_ids.add(kpi.kpi_id)

    rows: list[dict[str, float | int | str]] = []
    for _group_id, (group_name, kpi_ids) in grouped_kpis.items():
        measured = sum(
            1
            for measurement in dataset.measurements
            if measurement.period == period and measurement.kpi_id in kpi_ids
        )
        total = len(kpi_ids)
        coverage = round((measured / total) * 100, 1) if total else 0.0
        rows.append(
            {
                "Gruppe": group_name,
                "Erfasste KPIs": measured,
                "KPIs Gesamt": total,
                "Abdeckung %": coverage,
            }
        )

    return sorted(rows, key=lambda row: str(row["Gruppe"]).casefold())
