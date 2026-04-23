# KPI Dashboard

Streamlit-Dashboard für Innovationsprojekte mit JSON-Datenhaltung, Bootstrap aus einer Excel-Datei und einem deutschsprachigen Excel-Importpfad für regelmäßige KPI-Updates.

## Schnellstart

```bash
uv sync
uv run python -m kpi_dashboard.cli bootstrap
uv run streamlit run main.py
```

## Datenfluss

- `plan/Projektbericht Innovationsprojekte.xlsx` dient als fachlicher Seed für Projekte, KPI-Metadaten und Jahreszielwerte.
- `data/kpis.json` ist die operative Source of Truth.
- `data/kpis_demo.json` enthält deterministische Demo-Ist-Werte für den Frontend-Demomodus.
- Neue KPI-Stände werden über eine deutschsprachige Excel-Vorlage importiert.

## Demomodus

- Im Sidebar-Frontend kann `Demomodus` eingeschaltet werden.
- Dann verwendet die App `data/kpis_demo.json` statt `data/kpis.json`.

## Admin-Kommandos

```bash
uv run python -m kpi_dashboard.cli bootstrap
uv run python -m kpi_dashboard.cli create-template --period 2026-H1 --output data/import_2026-H1.xlsx
uv run python -m kpi_dashboard.cli import-template --input data/import_2026-H1.xlsx
uv run python -m kpi_dashboard.cli create-matrix-template --output data/import_matrix.xlsx
uv run python -m kpi_dashboard.cli import-matrix-template --input data/import_matrix.xlsx
```

## Matrix-Importvorlage

- Die Matrixvorlage erzeugt einen Reiter pro Projekt.
- Zeilen sind Berichtsperioden (`YYYY-H1` / `YYYY-H2`), Spalten sind Projekt-KPIs.
- KPI-Spalten zeigen die Einheit im Header (`KPI-Name [Einheit]`) und nutzen passende Zellformate.
- Leere Zellen bleiben beim Import unverändert (kein Löschen bestehender Ist-Werte).

## Qualitätschecks

```bash
uv run ruff check .
uv run ruff format .
uv run mypy .
uv run pytest
```
