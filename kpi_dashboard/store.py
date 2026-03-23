from __future__ import annotations

import tempfile
from pathlib import Path

from kpi_dashboard.bootstrap import build_dataset_from_workbook
from kpi_dashboard.models import KPIDataset


def load_dataset(data_path: Path) -> KPIDataset:
    return KPIDataset.model_validate_json(data_path.read_text(encoding="utf-8"))


def save_dataset(dataset: KPIDataset, data_path: Path) -> None:
    data_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=data_path.parent,
        delete=False,
        suffix=".tmp",
    ) as handle:
        handle.write(dataset.model_dump_json(indent=2))
        temp_path = Path(handle.name)
    temp_path.replace(data_path)


def load_or_bootstrap_dataset(data_path: Path, workbook_path: Path) -> KPIDataset:
    if data_path.exists():
        return load_dataset(data_path)

    dataset = build_dataset_from_workbook(workbook_path)
    save_dataset(dataset, data_path)
    return dataset
