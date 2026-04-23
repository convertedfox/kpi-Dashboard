from pathlib import Path

from openpyxl import load_workbook  # type: ignore[import-untyped]

from kpi_dashboard.bootstrap import build_dataset_from_workbook
from kpi_dashboard.importer import (
    create_import_template,
    create_matrix_import_template,
    import_matrix_template,
    import_template,
)
from kpi_dashboard.models import KPIValueKind
from kpi_dashboard.store import load_dataset, save_dataset

WORKBOOK_PATH = Path("plan/Projektbericht Innovationsprojekte.xlsx")


def test_import_template_roundtrip(tmp_path: Path) -> None:
    dataset = build_dataset_from_workbook(WORKBOOK_PATH)
    data_path = tmp_path / "kpis.json"
    template_path = tmp_path / "import_2032_H1.xlsx"
    save_dataset(dataset, data_path)

    create_import_template(dataset, "2032-H1", template_path)

    workbook = load_workbook(template_path)
    sheet = workbook.active
    kpis_by_id = {kpi.kpi_id: kpi for kpi in dataset.kpis}

    for row_index in range(2, sheet.max_row + 1):
        kpi_id = str(sheet.cell(row=row_index, column=4).value)
        kpi = kpis_by_id[kpi_id]
        if kpi.value_kind is KPIValueKind.BOOLEAN:
            sheet.cell(row=row_index, column=7).value = 1
        elif kpi.value_kind is KPIValueKind.ORDINAL:
            sheet.cell(row=row_index, column=7).value = kpi.max_value or 4
        else:
            sheet.cell(row=row_index, column=7).value = 12
    workbook.save(template_path)

    result = import_template(data_path, template_path)
    updated = load_dataset(data_path)
    imported_period_records = [
        record for record in updated.measurements if record.period == "2032-H1"
    ]

    assert result.period == "2032-H1"
    assert result.imported_records == len(dataset.kpis)
    assert len(imported_period_records) == len(dataset.kpis)


def test_import_template_rejects_missing_value(tmp_path: Path) -> None:
    dataset = build_dataset_from_workbook(WORKBOOK_PATH)
    data_path = tmp_path / "kpis.json"
    template_path = tmp_path / "invalid.xlsx"
    save_dataset(dataset, data_path)
    create_import_template(dataset, "2032-H2", template_path)

    workbook = load_workbook(template_path)
    sheet = workbook.active
    for row_index in range(3, sheet.max_row + 1):
        sheet.cell(row=row_index, column=7).value = 1
    workbook.save(template_path)

    try:
        import_template(data_path, template_path)
    except ValueError as error:
        assert "Wert fehlt" in str(error)
    else:
        raise AssertionError("Import ohne vollständige Werte hätte fehlschlagen müssen")


def test_create_matrix_import_template_creates_project_tabs_and_period_matrix(
    tmp_path: Path,
) -> None:
    dataset = build_dataset_from_workbook(WORKBOOK_PATH)
    template_path = tmp_path / "matrix.xlsx"

    create_matrix_import_template(dataset, template_path)

    workbook = load_workbook(template_path)
    assert "Anleitung" in workbook.sheetnames

    project_sheet = _project_sheet(workbook, "1.1")
    assert project_sheet.cell(row=2, column=1).value == "Berichtsperiode"
    assert project_sheet.cell(row=3, column=2).value == "1.1::roadmap-zur-umsetzung-des-hubs"

    periods = [project_sheet.cell(row=row_index, column=1).value for row_index in range(4, 8)]
    assert periods == ["2026-H1", "2026-H2", "2027-H1", "2027-H2"]


def test_import_matrix_template_imports_filled_cells(tmp_path: Path) -> None:
    dataset = build_dataset_from_workbook(WORKBOOK_PATH)
    data_path = tmp_path / "kpis.json"
    template_path = tmp_path / "matrix.xlsx"

    save_dataset(dataset, data_path)
    create_matrix_import_template(dataset, template_path)

    workbook = load_workbook(template_path)
    sheet_1_1 = _project_sheet(workbook, "1.1")
    row_2026_h1 = _period_row(sheet_1_1, "2026-H1")
    sheet_1_1.cell(row=row_2026_h1, column=2).value = "Ja"

    sheet_2_1 = _project_sheet(workbook, "2.1")
    row_2026_h1_2_1 = _period_row(sheet_2_1, "2026-H1")
    percentage_col = _kpi_column(sheet_2_1, "2.1::ubergangsquote-dhbw-ba-ma")
    sheet_2_1.cell(row=row_2026_h1_2_1, column=percentage_col).value = 60
    workbook.save(template_path)

    result = import_matrix_template(data_path, template_path)
    updated = load_dataset(data_path)
    records = {(record.kpi_id, record.period): record for record in updated.measurements}

    assert result.imported_records == 2
    assert result.imported_periods == ["2026-H1"]
    assert result.touched_projects == 2
    assert records[("1.1::roadmap-zur-umsetzung-des-hubs", "2026-H1")].value is True
    assert records[("2.1::ubergangsquote-dhbw-ba-ma", "2026-H1")].value == 60


def test_import_matrix_template_rejects_duplicate_kpi_period(tmp_path: Path) -> None:
    dataset = build_dataset_from_workbook(WORKBOOK_PATH)
    data_path = tmp_path / "kpis.json"
    template_path = tmp_path / "matrix.xlsx"

    save_dataset(dataset, data_path)
    create_matrix_import_template(dataset, template_path)

    workbook = load_workbook(template_path)
    project_sheet = _project_sheet(workbook, "1.1")
    row_2026_h1 = _period_row(project_sheet, "2026-H1")
    row_2026_h2 = _period_row(project_sheet, "2026-H2")
    project_sheet.cell(row=row_2026_h1, column=2).value = "Ja"
    project_sheet.cell(row=row_2026_h2, column=1).value = "2026-H1"
    project_sheet.cell(row=row_2026_h2, column=2).value = "Nein"
    workbook.save(template_path)

    try:
        import_matrix_template(data_path, template_path)
    except ValueError as error:
        assert "doppelte KPI-Periode" in str(error)
    else:
        raise AssertionError("Import mit doppelter KPI-Periode hätte fehlschlagen müssen")


def _project_sheet(workbook, project_id: str):
    for sheet in workbook.worksheets:
        if sheet.cell(row=1, column=2).value == project_id:
            return sheet
    raise AssertionError(f"Kein Projektblatt für {project_id} gefunden")


def _period_row(sheet, period: str) -> int:
    for row_index in range(4, sheet.max_row + 1):
        if sheet.cell(row=row_index, column=1).value == period:
            return row_index
    raise AssertionError(f"Periode {period} nicht gefunden")


def _kpi_column(sheet, kpi_id: str) -> int:
    for column_index in range(2, sheet.max_column + 1):
        if sheet.cell(row=3, column=column_index).value == kpi_id:
            return column_index
    raise AssertionError(f"KPI-Spalte {kpi_id} nicht gefunden")
