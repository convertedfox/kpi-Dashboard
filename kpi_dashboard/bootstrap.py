from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from kpi_dashboard.models import (
    KPIDataset,
    KPIDefinition,
    KPIValueKind,
    Project,
    TargetRecord,
    coerce_measurement_value,
)

GROUP_PATTERN = re.compile(r"^(?P<group_id>\d+)\.\s+(?P<name>.+)$")
PROJECT_PATTERN = re.compile(r"^(?P<project_id>\d+\.\d+)\s+(?P<name>.+)$")
ORDINAL_BULLETS_PATTERN = re.compile(r"(?P<max>\d+)\s+red-green-bullets?", re.IGNORECASE)
TRANSFERRED_COSTS_LABEL = "Überführte Kosten in Grundlast"


@dataclass(frozen=True)
class ProjectSeed:
    project_id: str
    project_name: str
    group_id: str
    group_name: str


def build_dataset_from_workbook(workbook_path: Path) -> KPIDataset:
    workbook = load_workbook(workbook_path, data_only=True)

    project_seeds = _parse_project_list(workbook["Projektliste"])
    kpis = _parse_kpi_sheet(workbook["KPIs"], project_seeds)
    portfolio_name, projects, targets = _parse_project_report(
        workbook["Projektbericht"], project_seeds, kpis
    )

    return KPIDataset(
        portfolio_name=portfolio_name,
        projects=projects,
        kpis=kpis,
        targets=sorted(targets, key=lambda target: (target.kpi_id, target.period)),
        measurements=[],
    )


def _parse_project_list(sheet: Worksheet) -> dict[str, ProjectSeed]:
    current_group: tuple[str, str] | None = None
    projects: dict[str, ProjectSeed] = {}

    for row in sheet.iter_rows(min_col=1, max_col=1, values_only=True):
        text = _clean_text(row[0])
        if not text:
            continue

        group_match = GROUP_PATTERN.match(text)
        if group_match:
            current_group = (
                group_match.group("group_id"),
                group_match.group("name").strip(),
            )
            continue

        project_match = PROJECT_PATTERN.match(text)
        if project_match and current_group is not None:
            project_id = project_match.group("project_id")
            projects[project_id] = ProjectSeed(
                project_id=project_id,
                project_name=project_match.group("name").strip(),
                group_id=current_group[0],
                group_name=current_group[1],
            )

    if not projects:
        raise ValueError("Keine Projekte in 'Projektliste' gefunden")
    return projects


def _parse_kpi_sheet(
    sheet: Worksheet, project_seeds: dict[str, ProjectSeed]
) -> list[KPIDefinition]:
    kpis: list[KPIDefinition] = []
    current_project_id: str | None = None

    for row_index in range(1, sheet.max_row + 1):
        group_or_portfolio = _clean_text(sheet.cell(row=row_index, column=1).value)
        project_or_kpi = _clean_text(sheet.cell(row=row_index, column=2).value)
        unit = _clean_text(sheet.cell(row=row_index, column=3).value)

        if group_or_portfolio and GROUP_PATTERN.match(group_or_portfolio):
            continue

        project_match = PROJECT_PATTERN.match(project_or_kpi)
        if project_match and not unit:
            current_project_id = project_match.group("project_id")
            if current_project_id not in project_seeds:
                raise ValueError(f"Unbekanntes Projekt in KPIs: {project_or_kpi}")
            continue

        if not project_or_kpi or not unit or current_project_id is None:
            continue

        seed = project_seeds[current_project_id]
        kpi_name = project_or_kpi
        display_hint = _clean_text(sheet.cell(row=row_index, column=6).value)
        value_kind, max_value = _infer_value_spec(unit, display_hint)
        kpis.append(
            KPIDefinition(
                kpi_id=f"{current_project_id}::{_slugify(kpi_name)}",
                project_id=seed.project_id,
                project_name=seed.project_name,
                group_id=seed.group_id,
                group_name=seed.group_name,
                kpi_name=kpi_name,
                unit=unit,
                source=_clean_text(sheet.cell(row=row_index, column=4).value),
                frequency=_clean_text(sheet.cell(row=row_index, column=5).value),
                display_hint=display_hint,
                data_logistics=_clean_text(sheet.cell(row=row_index, column=7).value),
                note=_clean_text(sheet.cell(row=row_index, column=8).value),
                value_kind=value_kind,
                max_value=max_value,
            )
        )

    if not kpis:
        raise ValueError("Keine KPI-Definitionen gefunden")
    return kpis


def _parse_project_report(
    sheet: Worksheet,
    project_seeds: dict[str, ProjectSeed],
    kpis: list[KPIDefinition],
) -> tuple[str, list[Project], list[TargetRecord]]:
    years = _extract_years(sheet)
    portfolio_name = _clean_text(sheet["B1"].value) or "Projekt-Controlling"
    targets: list[TargetRecord] = []
    current_project_id: str | None = None

    kpi_lookup = {(kpi.project_id, _normalize_key(kpi.kpi_name)): kpi for kpi in kpis}

    for row_index in range(7, sheet.max_row + 1):
        group_label = _clean_text(sheet.cell(row=row_index, column=2).value)
        project_or_metric = _clean_text(sheet.cell(row=row_index, column=3).value)

        if group_label and GROUP_PATTERN.match(group_label):
            current_project_id = None
            continue

        project_match = PROJECT_PATTERN.match(project_or_metric)
        if project_match:
            current_project_id = project_match.group("project_id")
            if current_project_id not in project_seeds:
                raise ValueError(f"Unbekanntes Projekt im Projektbericht: {project_or_metric}")
            continue

        if not current_project_id or not project_or_metric:
            continue

        if project_or_metric in {"Kosten", TRANSFERRED_COSTS_LABEL}:
            continue

        raw_year_values = _read_raw_year_values(sheet, row_index, years)
        if not raw_year_values:
            continue

        kpi = kpi_lookup.get((current_project_id, _normalize_key(project_or_metric)))
        if kpi is None:
            raise ValueError(
                f"KPI '{project_or_metric}' für Projekt {current_project_id} nicht in Stammdaten gefunden"
            )

        for year, raw_value in raw_year_values.items():
            targets.append(
                TargetRecord(
                    kpi_id=kpi.kpi_id,
                    period=f"{year}-H2",
                    value=coerce_measurement_value(raw_value, kpi.value_kind, kpi.max_value),
                )
            )

    projects = [
        Project(
            project_id=seed.project_id,
            project_name=seed.project_name,
            group_id=seed.group_id,
            group_name=seed.group_name,
        )
        for seed in sorted(project_seeds.values(), key=lambda item: item.project_id)
    ]

    return portfolio_name, projects, targets


def _infer_value_spec(unit: str, display_hint: str) -> tuple[KPIValueKind, int | None]:
    normalized_unit = unit.casefold()
    normalized_hint = display_hint.casefold()
    ordinal_match = ORDINAL_BULLETS_PATTERN.search(display_hint)

    if ordinal_match:
        return KPIValueKind.ORDINAL, int(ordinal_match.group("max"))
    if normalized_unit == "ja/nein" or "red-green-bullet" in normalized_hint:
        return KPIValueKind.BOOLEAN, None
    if normalized_unit == "euro":
        return KPIValueKind.CURRENCY, None
    if "%" in unit:
        return KPIValueKind.PERCENTAGE, None
    return KPIValueKind.NUMBER, None


def _extract_years(sheet: Worksheet) -> list[int]:
    years: list[int] = []
    for column in range(4, 10):
        raw_value = sheet.cell(row=3, column=column).value
        if raw_value is None:
            continue
        years.append(int(raw_value))
    return years


def _read_raw_year_values(sheet: Worksheet, row_index: int, years: list[int]) -> dict[int, object]:
    values: dict[int, object] = {}
    for offset, year in enumerate(years, start=4):
        raw_value = sheet.cell(row=row_index, column=offset).value
        if raw_value is None or str(raw_value).strip() == "":
            continue
        values[year] = raw_value
    return values


def _clean_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _normalize_key(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.casefold()).strip("-")
