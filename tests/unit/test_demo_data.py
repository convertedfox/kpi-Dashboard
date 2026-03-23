from pathlib import Path

from kpi_dashboard.bootstrap import build_dataset_from_workbook
from kpi_dashboard.demo_data import DEMO_IMPORTED_AT, build_demo_dataset
from kpi_dashboard.store import load_or_create_demo_dataset

WORKBOOK_PATH = Path("plan/Projektbericht Innovationsprojekte.xlsx")


def test_build_demo_dataset_creates_deterministic_demo_measurements() -> None:
    base_dataset = build_dataset_from_workbook(WORKBOOK_PATH)

    demo_dataset = build_demo_dataset(base_dataset)

    assert len(demo_dataset.projects) == len(base_dataset.projects)
    assert len(demo_dataset.kpis) == len(base_dataset.kpis)
    assert len(demo_dataset.targets) == len(base_dataset.targets)
    assert len(demo_dataset.measurements) == len(base_dataset.targets)
    assert all(record.origin == "demo" for record in demo_dataset.measurements)
    assert all(record.imported_at == DEMO_IMPORTED_AT for record in demo_dataset.measurements)

    keys = {(record.kpi_id, record.period) for record in demo_dataset.measurements}
    assert len(keys) == len(demo_dataset.measurements)


def test_load_or_create_demo_dataset_writes_demo_json(tmp_path: Path) -> None:
    data_path = tmp_path / "kpis.json"
    demo_path = tmp_path / "kpis_demo.json"

    demo_dataset = load_or_create_demo_dataset(demo_path, data_path, WORKBOOK_PATH)

    assert data_path.exists()
    assert demo_path.exists()
    assert len(demo_dataset.measurements) == len(demo_dataset.targets)
    assert all(record.origin == "demo" for record in demo_dataset.measurements)
