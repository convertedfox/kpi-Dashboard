from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook  # type: ignore[import-untyped]
from openpyxl.formatting.rule import FormulaRule  # type: ignore[import-untyped]
from openpyxl.styles import Font, PatternFill  # type: ignore[import-untyped]
from openpyxl.utils import get_column_letter  # type: ignore[import-untyped]
from openpyxl.worksheet.datavalidation import DataValidation  # type: ignore[import-untyped]

from kpi_dashboard.models import (
    KPIDataset,
    KPIDefinition,
    MeasurementRecord,
    KPIValueKind,
    coerce_measurement_value,
    period_sort_key,
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

MATRIX_GUIDE_SHEET_TITLE = "Anleitung"
MATRIX_PROJECT_ID_LABEL = "Projekt-ID"
MATRIX_PROJECT_NAME_LABEL = "Projektname"
MATRIX_PERIOD_HEADER = "Berichtsperiode"
MATRIX_HEADER_ROW = 2
MATRIX_KPI_ID_ROW = 3
MATRIX_DATA_START_ROW = 4

BOOLEAN_YES_VALUES = {"1", "ja", "true"}
BOOLEAN_NO_VALUES = {"0", "nein", "false"}

HEADER_FILLS: dict[KPIValueKind, PatternFill] = {
    KPIValueKind.BOOLEAN: PatternFill(fill_type="solid", fgColor="E7F4E4"),
    KPIValueKind.ORDINAL: PatternFill(fill_type="solid", fgColor="E9F2FF"),
    KPIValueKind.PERCENTAGE: PatternFill(fill_type="solid", fgColor="FFF4E5"),
    KPIValueKind.CURRENCY: PatternFill(fill_type="solid", fgColor="FBEAEA"),
    KPIValueKind.NUMBER: PatternFill(fill_type="solid", fgColor="F3F4F6"),
}


@dataclass(frozen=True)
class ImportResult:
    period: str
    imported_records: int


@dataclass(frozen=True)
class MatrixImportResult:
    imported_records: int
    imported_periods: list[str]
    touched_projects: int


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


def create_matrix_import_template(dataset: KPIDataset, output_path: Path) -> None:
    periods = _matrix_periods(dataset)
    if not periods:
        raise ValueError("Keine Berichtsperioden im Datensatz gefunden")

    workbook = Workbook()
    guide_sheet = workbook.active
    guide_sheet.title = MATRIX_GUIDE_SHEET_TITLE
    _write_matrix_guide_sheet(guide_sheet)

    projects = sorted(dataset.projects, key=lambda project: project.project_id)
    for project in projects:
        project_kpis = sorted(
            [kpi for kpi in dataset.kpis if kpi.project_id == project.project_id],
            key=lambda kpi: kpi.kpi_name.casefold(),
        )
        if not project_kpis:
            continue

        sheet_title = _unique_sheet_title(
            workbook,
            f"{project.project_id} {project.project_name}",
        )
        sheet = workbook.create_sheet(title=sheet_title)
        _write_matrix_project_sheet(
            sheet, project.project_id, project.project_name, project_kpis, periods
        )

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


def import_matrix_template(data_path: Path, template_path: Path) -> MatrixImportResult:
    dataset = load_dataset(data_path)
    workbook = load_workbook(template_path, data_only=True)

    projects_by_id = {project.project_id: project for project in dataset.projects}
    kpis_by_id = {kpi.kpi_id: kpi for kpi in dataset.kpis}

    imported_at = datetime.now(UTC)
    seen_keys: set[tuple[str, str]] = set()
    touched_projects: set[str] = set()
    periods: set[str] = set()
    imported_records: list[MeasurementRecord] = []

    for sheet in workbook.worksheets:
        if sheet.title == MATRIX_GUIDE_SHEET_TITLE:
            continue

        if _optional_text(sheet.cell(row=1, column=1).value) != MATRIX_PROJECT_ID_LABEL:
            raise ValueError(f"Reiter {sheet.title}: ungültiges Projektblatt")

        project_id = _required_sheet_text(
            sheet.title, sheet.cell(row=1, column=2).value, "Projekt-ID"
        )
        project = projects_by_id.get(project_id)
        if project is None:
            raise ValueError(f"Reiter {sheet.title}: unbekannte Projekt-ID {project_id}")

        project_name = _required_sheet_text(
            sheet.title,
            sheet.cell(row=1, column=4).value,
            "Projektname",
        )
        if project.project_name != project_name:
            raise ValueError(f"Reiter {sheet.title}: Projektname passt nicht zu {project_id}")

        if (
            _optional_text(sheet.cell(row=MATRIX_HEADER_ROW, column=1).value)
            != MATRIX_PERIOD_HEADER
        ):
            raise ValueError(f"Reiter {sheet.title}: Spalte A erwartet '{MATRIX_PERIOD_HEADER}'")

        kpi_columns = _read_matrix_kpi_columns(sheet.title, sheet, kpis_by_id, project_id)

        for row_index in range(MATRIX_DATA_START_ROW, sheet.max_row + 1):
            period_text = _optional_text(sheet.cell(row=row_index, column=1).value)
            if period_text is None:
                continue

            period = validate_period(period_text)
            for column_index, kpi in kpi_columns.items():
                raw_value = sheet.cell(row=row_index, column=column_index).value
                if raw_value in (None, ""):
                    continue

                key = (kpi.kpi_id, period)
                if key in seen_keys:
                    raise ValueError(
                        f"Reiter {sheet.title} Zeile {row_index}: doppelte KPI-Periode {kpi.kpi_id} {period}"
                    )
                seen_keys.add(key)

                imported_records.append(
                    MeasurementRecord(
                        kpi_id=kpi.kpi_id,
                        period=period,
                        value=coerce_measurement_value(raw_value, kpi.value_kind, kpi.max_value),
                        imported_at=imported_at,
                        origin="import-matrix",
                    )
                )
                periods.add(period)
                touched_projects.add(project_id)

    if not imported_records:
        raise ValueError("Keine Datensätze zum Import gefunden")

    merged_measurements = _merge_measurements(dataset, imported_records)
    updated_dataset = dataset.model_copy(update={"measurements": merged_measurements})
    save_dataset(updated_dataset, data_path)

    return MatrixImportResult(
        imported_records=len(imported_records),
        imported_periods=sorted(periods, key=period_sort_key),
        touched_projects=len(touched_projects),
    )


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


def _matrix_periods(dataset: KPIDataset) -> list[str]:
    source_periods = {target.period for target in dataset.targets}
    source_periods.update(measurement.period for measurement in dataset.measurements)

    years = {period_sort_key(period)[0] for period in source_periods}
    full_half_years = {f"{year}-H1" for year in years}
    full_half_years.update(f"{year}-H2" for year in years)
    return sorted(full_half_years, key=period_sort_key)


def _write_matrix_guide_sheet(sheet) -> None:
    sheet["A1"] = "Importanleitung"
    sheet["A1"].font = Font(bold=True)
    sheet["A3"] = "1) Trage Werte in den Projektreitern ein."
    sheet["A4"] = "2) Zeilen sind Berichtsperioden, Spalten sind KPIs."
    sheet["A5"] = "3) Leere Zellen bleiben unverändert und werden nicht importiert."
    sheet["A6"] = "4) Ja/Nein bitte als Ja, Nein, 1 oder 0 eintragen."
    sheet["A7"] = "5) Prozentwerte als Zahl zwischen 0 und 100 eintragen (z. B. 62,5)."
    sheet.column_dimensions["A"].width = 110


def _write_matrix_project_sheet(
    sheet,
    project_id: str,
    project_name: str,
    project_kpis: list[KPIDefinition],
    periods: list[str],
) -> None:
    sheet.cell(row=1, column=1, value=MATRIX_PROJECT_ID_LABEL).font = Font(bold=True)
    sheet.cell(row=1, column=2, value=project_id)
    sheet.cell(row=1, column=3, value=MATRIX_PROJECT_NAME_LABEL).font = Font(bold=True)
    sheet.cell(row=1, column=4, value=project_name)

    period_header = sheet.cell(row=MATRIX_HEADER_ROW, column=1, value=MATRIX_PERIOD_HEADER)
    period_header.font = Font(bold=True)

    for row_index, period in enumerate(periods, start=MATRIX_DATA_START_ROW):
        sheet.cell(row=row_index, column=1, value=period)

    for column_index, kpi in enumerate(project_kpis, start=2):
        header_cell = sheet.cell(
            row=MATRIX_HEADER_ROW,
            column=column_index,
            value=_matrix_kpi_header(kpi),
        )
        header_cell.font = Font(bold=True)
        header_cell.fill = HEADER_FILLS.get(kpi.value_kind, HEADER_FILLS[KPIValueKind.NUMBER])

        technical_cell = sheet.cell(row=MATRIX_KPI_ID_ROW, column=column_index, value=kpi.kpi_id)
        technical_cell.font = Font(color="6B7280")

        _apply_matrix_column_formatting(sheet, column_index, kpi, len(periods))

    sheet.row_dimensions[MATRIX_KPI_ID_ROW].hidden = True
    sheet.freeze_panes = f"B{MATRIX_DATA_START_ROW}"

    last_column = get_column_letter(len(project_kpis) + 1)
    last_row = MATRIX_DATA_START_ROW + len(periods) - 1
    sheet.auto_filter.ref = f"A{MATRIX_HEADER_ROW}:{last_column}{last_row}"
    sheet.column_dimensions["A"].width = 16

    for column_index in range(2, len(project_kpis) + 2):
        sheet.column_dimensions[get_column_letter(column_index)].width = 30


def _apply_matrix_column_formatting(
    sheet,
    column_index: int,
    kpi: KPIDefinition,
    period_count: int,
) -> None:
    start_row = MATRIX_DATA_START_ROW
    end_row = MATRIX_DATA_START_ROW + period_count - 1
    col_letter = get_column_letter(column_index)
    value_range = f"{col_letter}{start_row}:{col_letter}{end_row}"

    if kpi.value_kind is KPIValueKind.BOOLEAN:
        validation = DataValidation(
            type="list",
            formula1='"Ja,Nein"',
            allow_blank=True,
            promptTitle="Eingabehinweis",
            prompt="Bitte Ja oder Nein eintragen.",
        )
    elif kpi.value_kind is KPIValueKind.ORDINAL:
        upper_bound = str(kpi.max_value or 4)
        validation = DataValidation(
            type="whole",
            operator="between",
            formula1="0",
            formula2=upper_bound,
            allow_blank=True,
            promptTitle="Eingabehinweis",
            prompt=f"Bitte ganze Zahl zwischen 0 und {upper_bound} eintragen.",
        )
    elif kpi.value_kind is KPIValueKind.PERCENTAGE:
        validation = DataValidation(
            type="decimal",
            operator="between",
            formula1="0",
            formula2="100",
            allow_blank=True,
            promptTitle="Eingabehinweis",
            prompt="Bitte Prozentwert als Zahl zwischen 0 und 100 eintragen.",
        )
    else:
        validation = DataValidation(
            type="decimal",
            allow_blank=True,
            promptTitle="Eingabehinweis",
            prompt="Bitte numerischen Wert eintragen.",
        )

    sheet.add_data_validation(validation)
    validation.add(value_range)

    for row_index in range(start_row, end_row + 1):
        cell = sheet.cell(row=row_index, column=column_index)
        if kpi.value_kind is KPIValueKind.CURRENCY:
            cell.number_format = '#,##0.00 "EUR"'
        elif kpi.value_kind is KPIValueKind.PERCENTAGE:
            cell.number_format = '#,##0.00 " %"'
        elif kpi.value_kind in {KPIValueKind.NUMBER, KPIValueKind.ORDINAL}:
            cell.number_format = "#,##0.00" if kpi.value_kind is KPIValueKind.NUMBER else "0"

    if kpi.value_kind is KPIValueKind.BOOLEAN:
        true_fill = PatternFill(fill_type="solid", fgColor="E7F7EA")
        false_fill = PatternFill(fill_type="solid", fgColor="FDECEC")

        true_formula = [f'LOWER(TRIM({col_letter}{start_row}))="ja"']
        false_formula = [f'LOWER(TRIM({col_letter}{start_row}))="nein"']
        sheet.conditional_formatting.add(
            value_range,
            FormulaRule(formula=true_formula, stopIfTrue=False, fill=true_fill),
        )
        sheet.conditional_formatting.add(
            value_range,
            FormulaRule(formula=false_formula, stopIfTrue=False, fill=false_fill),
        )


def _matrix_kpi_header(kpi: KPIDefinition) -> str:
    return f"{kpi.kpi_name} [{kpi.unit}]"


def _read_matrix_kpi_columns(
    sheet_title: str,
    sheet,
    kpis_by_id: dict[str, KPIDefinition],
    project_id: str,
) -> dict[int, KPIDefinition]:
    kpi_columns: dict[int, KPIDefinition] = {}
    column_index = 2
    while True:
        kpi_id = _optional_text(sheet.cell(row=MATRIX_KPI_ID_ROW, column=column_index).value)
        header = _optional_text(sheet.cell(row=MATRIX_HEADER_ROW, column=column_index).value)
        if kpi_id is None and header is None:
            break
        if kpi_id is None:
            raise ValueError(f"Reiter {sheet_title}: fehlende KPI-ID in Spalte {column_index}")

        kpi = kpis_by_id.get(kpi_id)
        if kpi is None:
            raise ValueError(f"Reiter {sheet_title}: unbekannte KPI-ID {kpi_id}")
        if kpi.project_id != project_id:
            raise ValueError(
                f"Reiter {sheet_title}: KPI {kpi_id} gehört nicht zu Projekt {project_id}"
            )

        expected_header = _matrix_kpi_header(kpi)
        if header != expected_header:
            raise ValueError(
                f"Reiter {sheet_title}: KPI-Spalte {column_index} hat einen ungültigen Titel"
            )

        kpi_columns[column_index] = kpi
        column_index += 1

    if not kpi_columns:
        raise ValueError(f"Reiter {sheet_title}: keine KPI-Spalten gefunden")
    return kpi_columns


def _unique_sheet_title(workbook: Workbook, candidate: str) -> str:
    invalid_chars = {"[", "]", ":", "*", "?", "/", "\\"}
    cleaned = "".join("-" if char in invalid_chars else char for char in candidate).strip()
    if not cleaned:
        cleaned = "Projekt"
    base = cleaned[:31]
    if base not in workbook.sheetnames:
        return base

    index = 2
    while True:
        suffix = f" ({index})"
        truncated = base[: 31 - len(suffix)]
        proposal = f"{truncated}{suffix}"
        if proposal not in workbook.sheetnames:
            return proposal
        index += 1


def _required_sheet_text(sheet_title: str, value: object, label: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"Reiter {sheet_title}: {label} fehlt")
    return text


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
