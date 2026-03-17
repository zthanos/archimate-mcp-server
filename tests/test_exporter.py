from archimate_mcp.builders import build_model_with_default_view
from archimate_mcp.exporter import export_archimate_exchange_xml
from archimate_mcp.models import ArchimateModel


def test_exporter_contains_expected_sections():
    model = ArchimateModel.model_validate(
        {
            "model": {"id": "m1", "name": "Test Model"},
            "elements": [
                {"id": "app", "type": "ApplicationComponent", "name": "App"},
                {"id": "svc", "type": "ApplicationService", "name": "Svc"},
            ],
            "relationships": [
                {
                    "id": "r1",
                    "type": "Realization",
                    "source": "app",
                    "target": "svc",
                },
                {
                    "id": "r2",
                    "type": "Serving",
                    "source": "svc",
                    "target": "app",
                },
            ],
            "views": [],
        }
    )

    built = build_model_with_default_view(model)
    xml = export_archimate_exchange_xml(built)

    assert "<model" in xml
    assert "<elements>" in xml
    assert "<relationships>" in xml
    assert "<views>" in xml
    assert "Test Model" in xml
    assert "view_default_application" in xml
