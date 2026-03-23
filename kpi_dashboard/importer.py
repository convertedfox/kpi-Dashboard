from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook  # type: ignore[import-untyped]
from openpyxl.styles import Font  # type: ignore[import-untyped]

from kpi_dashboard.models import (
    KPIDataset,
    MeasurementRecord,
    coerce_measurement_value,
    validate_period,
)
from kpi_dashboard.store import load_dataset, save_dataset

TEMPLATE_HEADERS = [
    "Berichtsperiode",
    "Projekt-ID",
    "Projektname",
    "KPI-ID",
    "KPI-Name",
    "Einheit",
    "Wert",
    "Kommentar",
]


@dataclass(frozen=True)
class ImportResult:
    period: str
    imported_records: int


def create_import_template(dataset: KPIDataset, period: str, output_path: Path) -> None:
    validated_period = validate_period(period)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Importvorlage"
    sheet.append(TEMPLATE_HEADERS)

    for cell in sheet[1]:
        cell.font = Font(bold=True)

    ordered_kpis = sorted(
        dataset.kpis,
        key=lambda kpi: (kpi.group_id, kpi.project_id, kpi.kpi_name.casefold()),
    )
    for kpi in ordered_kpis:
        sheet.append(
            [
                validated_period,
                kpi.project_id,
                kpi.project_name,
                kpi.kpi_id,
                kpi.kpi_name,
                kpi.unit,
                "",
                "",
            ]
        )

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)


def import_template(data_path: Path, template_path: Path) -> ImportResult:
    dataset = load_dataset(data_path)
    workbook = load_workbook(template_path, data_only=True)
    sheet = workbook.active

    headers = [
        sheet.cell(row=1, column=index).value for index in range(1, len(TEMPLATE_HEADERS) + 1)
    ]
    if headers != TEMPLATE_HEADERS:
        raise ValueError("Importvorlage hat ungültige Spalten")

    projects_by_id = {project.project_id: project for project in dataset.projects}
    kpis_by_id = {kpi.kpi_id: kpi for kpi in dataset.kpis}
    imported_at = datetime.now(UTC)
    seen_keys: set[tuple[str, str]] = set()
    periods: set[str] = set()
    imported_records: list[MeasurementRecord] = []

    for row_index, row in enumerate(
        sheet.iter_rows(min_row=2, max_col=len(TEMPLATE_HEADERS), values_only=True),
        start=2,
    ):
        if all(value in (None, "") for value in row):
            continue

        period = validate_period(_required_text(row[0], row_index, "Berichtsperiode"))
        project_id = _required_text(row[1], row_index, "Projekt-ID")
        project_name = _required_text(row[2], row_index, "Projektname")
        kpi_id = _required_text(row[3], row_index, "KPI-ID")
        kpi_name = _required_text(row[4], row_index, "KPI-Name")
        unit = _required_text(row[5], row_index, "Einheit")
        raw_value = row[6]
        comment = _optional_text(row[7])

        project = projects_by_id.get(project_id)
        if project is None:
            raise ValueError(f"Zeile {row_index}: unbekannte Projekt-ID {project_id}")
        if project.project_name != project_name:
            raise ValueError(f"Zeile {row_index}: Projektname passt nicht zu {project_id}")

        kpi = kpis_by_id.get(kpi_id)
        if kpi is None:
            raise ValueError(f"Zeile {row_index}: unbekannte KPI-ID {kpi_id}")
        if kpi.project_id != project_id:
            raise ValueError(
                f"Zeile {row_index}: KPI {kpi_id} gehört nicht zu Projekt {project_id}"
            )
        if kpi.kpi_name != kpi_name:
            raise ValueError(f"Zeile {row_index}: KPI-Name passt nicht zu {kpi_id}")
        if kpi.unit != unit:
            raise ValueError(f"Zeile {row_index}: Einheit passt nicht zu {kpi_id}")
        if raw_value in (None, ""):
            raise ValueError(f"Zeile {row_index}: Wert fehlt")

        key = (kpi_id, period)
        if key in seen_keys:
            raise ValueError(f"Zeile {row_index}: doppelte KPI für Periode {period}")
        seen_keys.add(key)
        periods.add(period)

        imported_records.append(
            MeasurementRecord(
                kpi_id=kpi_id,
                period=period,
                value=coerce_measurement_value(raw_value, kpi.value_kind, kpi.max_value),
                comment=comment,
                imported_at=imported_at,
                origin="import-template",
            )
        )

    if not imported_records:
        raise ValueError("Keine Datensätze zum Import gefunden")
    if len(periods) != 1:
        raise ValueError("Eine Importdatei darf nur genau eine Berichtsperiode enthalten")

    merged_measurements = _merge_measurements(dataset, imported_records)
    updated_dataset = dataset.model_copy(update={"measurements": merged_measurements})
    save_dataset(updated_dataset, data_path)
    return ImportResult(period=next(iter(periods)), imported_records=len(imported_records))


def _merge_measurements(
    dataset: KPIDataset, imported_records: list[MeasurementRecord]
) -> list[MeasurementRecord]:
    records_by_key = {
        (measurement.kpi_id, measurement.period): measurement
        for measurement in dataset.measurements
    }
    for record in imported_records:
        records_by_key[(record.kpi_id, record.period)] = record

    return sorted(
        records_by_key.values(),
        key=lambda measurement: (measurement.kpi_id, measurement.period),
    )


def _required_text(value: object, row_index: int, label: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"Zeile {row_index}: {label} fehlt")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
