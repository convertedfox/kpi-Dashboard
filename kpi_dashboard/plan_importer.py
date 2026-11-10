"""Import the revised 2026 planning matrix without creating actual measurements."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import load_workbook

from kpi_dashboard.importer import import_matrix_template
from kpi_dashboard.models import (
    KPIDefinition,
    KPIValueKind,
    KPIRenderType,
    PlannedMilestone,
    TargetRecord,
)
from kpi_dashboard.store import load_dataset, save_dataset


@dataclass(frozen=True)
class PlanImportResult:
    target_count: int
    milestone_count: int
    status_count: int


# New meanings receive new IDs so historical targets cannot change meaning.
REPLACEMENTS = {
    "1.3::erfolgreiche-match-makings": (
        "1.3::anzahl-buchende-teilnehmende",
        "Anzahl buchende Teilnehmende",
        "Anzahl",
        KPIValueKind.NUMBER,
        KPIRenderType.BALKEN,
    ),
    "3.1::beratungsgesprache-mit-modul-o-mat": (
        "3.1::anteil-beratungsgesprache-mit-modul-o-mat",
        "Beratungsgespräche mit Modul-O-Mat",
        "%",
        KPIValueKind.PERCENTAGE,
        KPIRenderType.FORTSCHRITT,
    ),
    "3.2::prozesse-uber-zus-infrastruktur": (
        "3.2::ctr",
        "CTR",
        "%",
        KPIValueKind.PERCENTAGE,
        KPIRenderType.FORTSCHRITT,
    ),
}
MILESTONE_IDS = {
    "1.2::mvp-mit-validiertem-tool-und-prozess",
    "1.2::produktionsreifes-tool",
}


def import_plan_matrix(data_path: Path, input_path: Path) -> PlanImportResult:
    """Validate the full revised workbook, then atomically upsert plans only.

    This is an explicit migration for the revised matrix, not a permissive
    header-matching importer. Unrecognized changes still fail validation.
    """
    dataset = load_dataset(data_path)
    workbook = load_workbook(input_path, data_only=True)
    definitions = {item.kpi_id: item for item in dataset.kpis}
    retired = set(REPLACEMENTS) | MILESTONE_IDS
    if any(item.kpi_id in retired for item in dataset.measurements):
        raise ValueError("Ersetzte KPIs besitzen Ist-Werte; fachliche Migration erforderlich")

    for old_id, (new_id, name, unit, kind, render) in REPLACEMENTS.items():
        if old_id in definitions:
            old = definitions.pop(old_id)
            definitions[new_id] = old.model_copy(
                update={
                    "kpi_id": new_id,
                    "kpi_name": name,
                    "unit": unit,
                    "value_kind": kind,
                    "render_type": render,
                    "note": f"Planmatrix 2026: ersetzt {old_id}; alte Ziele nicht übernommen.",
                }
            )
    for old_id in MILESTONE_IDS:
        definitions.pop(old_id, None)

    for project_id, name, new_id in [
        ("1.3", "Anzahl Beratung Unternehmen", "1.3::anzahl-beratung-unternehmen"),
        ("3.2", "Zugriffe auf ZuS-Shop", "3.2::zugriffe-auf-zus-shop"),
    ]:
        project = next(item for item in dataset.projects if item.project_id == project_id)
        definitions.setdefault(
            new_id,
            KPIDefinition(
                **project.model_dump(),
                kpi_id=new_id,
                kpi_name=name,
                unit="Anzahl",
                source="Planmatrix",
                frequency="1/2 jährlich",
                display_hint="Balken-Diagramm",
                render_type=KPIRenderType.BALKEN,
                data_logistics="Excel-Import",
                value_kind=KPIValueKind.NUMBER,
            ),
        )

    milestones = {(item.project_id, item.period): item for item in dataset.planned_milestones}
    imported_milestones = 0
    imported_statuses = 0
    seen_milestones: set[tuple[str, str]] = set()
    for sheet in workbook.worksheets:
        if sheet.title == "Anleitung":
            continue
        project_id = sheet["B1"].value
        if project_id == "1.2":
            if [sheet.cell(2, col).value for col in (3, 4)] != [
                "Meilenstein",
                "Erreichungsgrad",
            ] or [sheet.cell(3, col).value for col in (3, 4)] != [
                "1.2::mvp-mit-validiertem-tool-und-prozess",
                "1.2::produktionsreifes-tool",
            ]:
                raise ValueError("Projekt 1.2: unerwartete Meilensteinspalten")
            for row in range(4, sheet.max_row + 1):
                period, name, status = (sheet.cell(row, col).value for col in (1, 3, 4))
                if name is None and status is None:
                    continue
                if not period or not name:
                    raise ValueError(f"Projekt 1.2 Zeile {row}: Periode oder Meilenstein fehlt")
                key = ("1.2", str(period))
                if key in seen_milestones:
                    raise ValueError(f"Projekt 1.2: doppelter Meilenstein für {period}")
                seen_milestones.add(key)
                previous = milestones.get(key)
                milestones[key] = PlannedMilestone(
                    project_id="1.2",
                    period=str(period),
                    name=str(name),
                    planned_status=str(status)
                    if status is not None
                    else (previous.planned_status if previous else None),
                )
                imported_milestones += 1
                imported_statuses += status is not None
            project_name = sheet["D1"].value
            sheet.delete_cols(3, 2)
            sheet["C1"] = "Projektname"
            sheet["D1"] = project_name
        if project_id == "3.2" and sheet["D1"].value is None:
            if sheet["E1"].value != "ZuS Infrastruktur incl Shop":
                raise ValueError("Projekt 3.2: Projektname fehlt")
            sheet["D1"] = sheet["E1"].value
            sheet["E1"] = None

        for col in range(2, sheet.max_column + 1):
            old_id = sheet.cell(3, col).value
            header = sheet.cell(2, col).value
            if old_id in REPLACEMENTS:
                new_id, name, unit, _, _ = REPLACEMENTS[old_id]
                expected_unit = "Anteil" if str(old_id).startswith("3.1::") else unit
                if header != f"{name} [{expected_unit}]":
                    raise ValueError(f"Projekt {project_id}: unerwarteter Titel {header}")
                sheet.cell(3, col).value = new_id
                sheet.cell(2, col).value = f"{name} [{unit}]"
            elif old_id is None and header:
                new_column_id = {
                    (
                        "1.3",
                        "Anzahl Beratung Unternehmen [Anzahl]",
                    ): "1.3::anzahl-beratung-unternehmen",
                    ("3.2", "Zugriffe auf ZuS-Shop [Anzahl]"): "3.2::zugriffe-auf-zus-shop",
                }.get((str(project_id), str(header)))
                if new_column_id:
                    sheet.cell(3, col).value = new_column_id

    staged = dataset.model_copy(
        update={
            "kpis": sorted(definitions.values(), key=lambda item: item.kpi_id),
            "measurements": [],
        }
    )
    # Reuse strict project, header, ID, type and duplicate validation, isolated
    # from the operative file. Its records become targets, never actuals.
    with TemporaryDirectory() as temp:
        temp_data = Path(temp) / "plans.json"
        temp_workbook = Path(temp) / "plans.xlsx"
        save_dataset(staged, temp_data)
        workbook.save(temp_workbook)
        result = import_matrix_template(temp_data, temp_workbook)
        imported = load_dataset(temp_data).measurements

    targets = {
        (item.kpi_id, item.period): item for item in dataset.targets if item.kpi_id not in retired
    }
    for record in imported:
        targets[(record.kpi_id, record.period)] = TargetRecord(
            kpi_id=record.kpi_id,
            period=record.period,
            value=record.value,
        )
    updated = dataset.model_copy(
        update={
            "kpis": staged.kpis,
            "targets": sorted(targets.values(), key=lambda item: (item.kpi_id, item.period)),
            "planned_milestones": sorted(
                milestones.values(),
                key=lambda item: (item.project_id, item.period),
            ),
        }
    )
    save_dataset(updated, data_path)
    return PlanImportResult(result.imported_records, imported_milestones, imported_statuses)
