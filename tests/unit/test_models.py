from kpi_dashboard.models import KPIDefinition, KPIRenderType, KPIValueKind


def test_kpi_definition_fills_render_type_for_existing_json_payloads() -> None:
    definition = KPIDefinition.model_validate(
        {
            "kpi_id": "1.2::mvp",
            "project_id": "1.2",
            "project_name": "Skill Gap Analyzer",
            "group_id": "1",
            "group_name": "Matchmaking, Vermarktung und Vertrieb",
            "kpi_name": "MVP mit validiertem Tool und Prozess",
            "unit": "Ja/Nein",
            "source": "Test",
            "frequency": "halbjährlich",
            "display_hint": "Red-Green-Bullet",
            "data_logistics": "manuell",
            "value_kind": "boolean",
        }
    )

    assert definition.render_type is KPIRenderType.AMPEL
    assert definition.value_kind is KPIValueKind.BOOLEAN
