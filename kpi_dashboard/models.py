from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator

PERIOD_PATTERN = re.compile(r"^\d{4}-H[12]$")
KPIValue: TypeAlias = bool | int | float


class KPIValueKind(StrEnum):
    BOOLEAN = "boolean"
    CURRENCY = "currency"
    NUMBER = "number"
    ORDINAL = "ordinal"
    PERCENTAGE = "percentage"


def validate_period(period: str) -> str:
    if not PERIOD_PATTERN.match(period):
        raise ValueError(f"ungültige Periode: {period}")
    return period


def period_sort_key(period: str) -> tuple[int, int]:
    validate_period(period)
    year_text, half_text = period.split("-", maxsplit=1)
    return int(year_text), int(half_text[-1])


def coerce_measurement_value(
    raw_value: object, kind: KPIValueKind, max_value: int | None = None
) -> KPIValue:
    if kind is KPIValueKind.BOOLEAN:
        if isinstance(raw_value, bool):
            return raw_value
        normalized = str(raw_value).strip().casefold()
        if normalized in {"1", "ja", "true"}:
            return True
        if normalized in {"0", "nein", "false"}:
            return False
        raise ValueError(f"ungültiger Boolean-Wert: {raw_value}")

    if kind is KPIValueKind.ORDINAL:
        if raw_value is None or str(raw_value).strip() == "":
            raise ValueError("leerer Wert ist nicht erlaubt")
        ordinal_value = int(float(str(raw_value).strip()))
        upper_bound = max_value or 4
        if ordinal_value < 0 or ordinal_value > upper_bound:
            raise ValueError(f"ungültiger Ordinal-Wert: {raw_value}")
        return ordinal_value

    if raw_value is None or str(raw_value).strip() == "":
        raise ValueError("leerer Wert ist nicht erlaubt")

    numeric_value = float(str(raw_value).strip().replace(",", "."))
    if numeric_value.is_integer():
        return int(numeric_value)
    return numeric_value


def format_value(
    value: KPIValue, kind: KPIValueKind, unit: str, max_value: int | None = None
) -> str:
    if kind is KPIValueKind.BOOLEAN:
        return "Ja" if bool(value) else "Nein"
    if kind is KPIValueKind.ORDINAL:
        upper_bound = max_value or 4
        return f"{int(value)} / {upper_bound}"

    numeric = float(value)
    precision = 0 if numeric.is_integer() else 2
    formatted = f"{numeric:,.{precision}f}"
    localized = formatted.replace(",", "_").replace(".", ",").replace("_", ".")

    if kind is KPIValueKind.CURRENCY:
        return f"{localized} EUR"
    if kind is KPIValueKind.PERCENTAGE:
        return f"{localized} %"
    if unit and unit.casefold() != "anzahl":
        return f"{localized} {unit}"
    return localized


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    project_name: str
    group_id: str
    group_name: str


class KPIDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kpi_id: str
    project_id: str
    project_name: str
    group_id: str
    group_name: str
    kpi_name: str
    unit: str
    source: str
    frequency: str
    display_hint: str
    data_logistics: str
    note: str = ""
    value_kind: KPIValueKind
    max_value: int | None = None


class MeasurementRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kpi_id: str
    period: str
    value: KPIValue
    comment: str | None = None
    imported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    origin: str = "manual"

    @field_validator("period")
    @classmethod
    def validate_measurement_period(cls, value: str) -> str:
        return validate_period(value)


class TargetRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kpi_id: str
    period: str
    value: KPIValue

    @field_validator("period")
    @classmethod
    def validate_target_period(cls, value: str) -> str:
        return validate_period(value)


class KPIDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_name: str
    projects: list[Project]
    kpis: list[KPIDefinition]
    targets: list[TargetRecord]
    measurements: list[MeasurementRecord]
