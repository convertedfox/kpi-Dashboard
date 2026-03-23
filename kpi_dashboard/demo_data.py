from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from kpi_dashboard.models import KPIDataset, KPIValue, KPIValueKind, MeasurementRecord

DEMO_IMPORTED_AT = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


def build_demo_dataset(base_dataset: KPIDataset) -> KPIDataset:
    measurements: list[MeasurementRecord] = []
    kpis_by_id = {kpi.kpi_id: kpi for kpi in base_dataset.kpis}

    for target in sorted(base_dataset.targets, key=lambda item: (item.kpi_id, item.period)):
        kpi = kpis_by_id[target.kpi_id]
        score = _stable_score(target.kpi_id, target.period)
        status = _demo_status(score)
        measurements.append(
            MeasurementRecord(
                kpi_id=target.kpi_id,
                period=target.period,
                value=_build_demo_value(target.value, kpi.value_kind, kpi.max_value, status),
                comment=f"Demowert: {_demo_comment(status)}",
                imported_at=DEMO_IMPORTED_AT,
                origin="demo",
            )
        )

    return base_dataset.model_copy(update={"measurements": measurements})


def _stable_score(kpi_id: str, period: str) -> int:
    digest = sha256(f"{kpi_id}:{period}".encode("utf-8")).digest()
    return digest[0]


def _demo_status(score: int) -> str:
    remainder = score % 4
    if remainder == 0:
        return "reached"
    if remainder == 1:
        return "behind"
    if remainder == 2:
        return "stretch"
    return "behind"


def _build_demo_value(
    target_value: KPIValue,
    value_kind: KPIValueKind,
    max_value: int | None,
    status: str,
) -> KPIValue:
    if value_kind is KPIValueKind.BOOLEAN:
        if status in {"reached", "stretch"}:
            return bool(target_value)
        return not bool(target_value)

    if value_kind is KPIValueKind.ORDINAL:
        target_int = int(target_value)
        upper_bound = max_value or 4
        if status == "stretch":
            return min(target_int + 1, upper_bound)
        if status == "reached":
            return target_int
        return max(target_int - 1, 0)

    target_float = float(target_value)
    if status == "stretch":
        return _normalize_numeric(target_float * 1.15)
    if status == "reached":
        return _normalize_numeric(target_float)
    if target_float <= 0:
        return _normalize_numeric(0.0)
    return _normalize_numeric(target_float * 0.82)


def _normalize_numeric(value: float) -> int | float:
    return int(value) if value.is_integer() else round(value, 2)


def _demo_comment(status: str) -> str:
    comments = {
        "reached": "Ziel erreicht",
        "behind": "unter Ziel",
        "stretch": "über Ziel",
    }
    return comments[status]
