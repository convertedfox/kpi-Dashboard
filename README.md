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

Die Admin-CLI wird immer so aufgerufen:

```bash
uv run python -m kpi_dashboard.cli <kommando> [optionen]
```

### 1) `bootstrap`

Erzeugt den initialen JSON-Datenstand aus der fachlichen Excel-Datei.

```bash
uv run python -m kpi_dashboard.cli bootstrap
```

Optionale Parameter:

- `--source`: Pfad zur Seed-Excel (Default: `plan/Projektbericht Innovationsprojekte.xlsx`)
- `--output`: Zielpfad der operativen JSON-Datei (Default: `data/kpis.json`)

Beispiel mit expliziten Pfaden:

```bash
uv run python -m kpi_dashboard.cli bootstrap --source plan/Projektbericht\ Innovationsprojekte.xlsx --output data/kpis.json
```

### 2) `create-template`

Erzeugt die klassische, zeilenbasierte Importvorlage fuer genau eine Berichtsperiode.

```bash
uv run python -m kpi_dashboard.cli create-template --period 2026-H1 --output data/import_2026-H1.xlsx
```

Optionale/erforderliche Parameter:

- `--data`: Quelle fuer Projekte/KPIs (Default: `data/kpis.json`)
- `--period`: Berichtsperiode im Format `YYYY-H1` oder `YYYY-H2` (Pflicht)
- `--output`: Zielpfad der erzeugten Excel-Vorlage (Pflicht)

### 3) `import-template`

Importiert eine ausgefuellte, zeilenbasierte Vorlage in `data/kpis.json`.

```bash
uv run python -m kpi_dashboard.cli import-template --input data/import_2026-H1.xlsx
```

Parameter:

- `--data`: Ziel-JSON (Default: `data/kpis.json`)
- `--input`: Pfad zur ausgefuellten Vorlage (Pflicht)

Hinweis: Die Datei darf genau eine Berichtsperiode enthalten.

### 4) `create-matrix-template`

Erzeugt eine userfreundliche Matrixvorlage:

- ein Reiter pro Projekt
- Zeilen = Berichtsperioden
- Spalten = KPIs inkl. Einheit im Header

```bash
uv run python -m kpi_dashboard.cli create-matrix-template --output data/import_matrix.xlsx
```

Parameter:

- `--data`: Quelle fuer Projekte/KPIs (Default: `data/kpis.json`)
- `--output`: Zielpfad der Matrixvorlage (Pflicht)

### 5) `import-matrix-template`

Importiert eine ausgefuellte Matrixvorlage in `data/kpis.json`.

```bash
uv run python -m kpi_dashboard.cli import-matrix-template --input data/import_matrix.xlsx
```

Parameter:

- `--data`: Ziel-JSON (Default: `data/kpis.json`)
- `--input`: Pfad zur ausgefuellten Matrixvorlage (Pflicht)

Hinweise:

- Es werden nur bestehende Projekte/KPIs befuellt.
- Leere Zellen werden ignoriert (kein Loeschen bestehender Ist-Werte).
- Werte werden pro `(kpi_id, period)` aktualisiert (Upsert-Verhalten).

### Typischer Ablauf

```bash
# 1) Initialen Datenstand aus dem Workbook erzeugen
uv run python -m kpi_dashboard.cli bootstrap

# 2) Matrixvorlage erzeugen
uv run python -m kpi_dashboard.cli create-matrix-template --output data/import_matrix.xlsx

# 3) Vorlage manuell befuellen (Excel)

# 4) Werte importieren
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
