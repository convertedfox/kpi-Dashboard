from pathlib import Path

from openpyxl import load_workbook  # type: ignore[import-untyped]

from kpi_dashboard.bootstrap import build_dataset_from_workbook
from kpi_dashboard.importer import create_import_template, import_template
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
