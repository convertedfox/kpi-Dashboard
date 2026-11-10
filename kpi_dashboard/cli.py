from __future__ import annotations

import argparse
from pathlib import Path

from kpi_dashboard.bootstrap import build_dataset_from_workbook
from kpi_dashboard.importer import (
    create_import_template,
    create_matrix_import_template,
    import_matrix_template,
    import_template,
)
from kpi_dashboard.plan_importer import import_plan_matrix
from kpi_dashboard.store import load_dataset, save_dataset

DEFAULT_WORKBOOK_PATH = Path("plan/Projektbericht Innovationsprojekte.xlsx")
DEFAULT_DATA_PATH = Path("data/kpis.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Admin-Kommandos für das KPI-Dashboard")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Seed-Workbook in JSON überführen")
    bootstrap_parser.add_argument("--source", type=Path, default=DEFAULT_WORKBOOK_PATH)
    bootstrap_parser.add_argument("--output", type=Path, default=DEFAULT_DATA_PATH)

    template_parser = subparsers.add_parser(
        "create-template",
        help="Deutschsprachige Importvorlage für eine Berichtsperiode erzeugen",
    )
    template_parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    template_parser.add_argument("--period", required=True)
    template_parser.add_argument("--output", type=Path, required=True)

    import_parser = subparsers.add_parser(
        "import-template",
        help="Ausgefüllte Excel-Vorlage in das JSON importieren",
    )
    import_parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    import_parser.add_argument("--input", type=Path, required=True)

    matrix_template_parser = subparsers.add_parser(
        "create-matrix-template",
        help="Projektweise Matrixvorlage mit Halbjahreszeilen erzeugen",
    )
    matrix_template_parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    matrix_template_parser.add_argument("--output", type=Path, required=True)

    matrix_import_parser = subparsers.add_parser(
        "import-matrix-template",
        help="Ausgefüllte Matrixvorlage in das JSON importieren",
    )
    matrix_import_parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    matrix_import_parser.add_argument("--input", type=Path, required=True)

    plan_parser = subparsers.add_parser(
        "import-plan-matrix", help="Überarbeitete Planmatrix 2026 als Sollwerte importieren"
    )
    plan_parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    plan_parser.add_argument("--input", type=Path, required=True)

    arguments = parser.parse_args()

    if arguments.command == "import-plan-matrix":
        result = import_plan_matrix(arguments.data, arguments.input)
        print(
            f"Planimport abgeschlossen: {result.target_count} Sollwerte, "
            f"{result.milestone_count} Meilensteine, {result.status_count} Planstatus"
        )
        return

    if arguments.command == "bootstrap":
        dataset = build_dataset_from_workbook(arguments.source)
        save_dataset(dataset, arguments.output)
        print(
            f"Bootstrap abgeschlossen: {len(dataset.projects)} Projekte, "
            f"{len(dataset.kpis)} KPIs, {len(dataset.targets)} Zielwerte"
        )
        return

    if arguments.command == "create-template":
        dataset = load_dataset(arguments.data)
        create_import_template(dataset, arguments.period, arguments.output)
        print(f"Vorlage geschrieben: {arguments.output}")
        return

    if arguments.command == "import-template":
        import_result = import_template(arguments.data, arguments.input)
        print(
            "Import abgeschlossen: "
            f"{import_result.imported_records} Datensätze für {import_result.period}"
        )
        return

    if arguments.command == "create-matrix-template":
        dataset = load_dataset(arguments.data)
        create_matrix_import_template(dataset, arguments.output)
        print(f"Matrixvorlage geschrieben: {arguments.output}")
        return

    if arguments.command == "import-matrix-template":
        matrix_result = import_matrix_template(arguments.data, arguments.input)
        periods_text = ", ".join(matrix_result.imported_periods)
        print(
            "Matrix-Import abgeschlossen: "
            f"{matrix_result.imported_records} Datensätze, "
            f"{matrix_result.touched_projects} Projekte, "
            f"Perioden: {periods_text}"
        )


if __name__ == "__main__":
    main()
