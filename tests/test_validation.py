from archimate_mcp.models import ArchimateModel
from archimate_mcp.validation import validate_model


def test_validate_model_happy_path():
    model = ArchimateModel.model_validate(
        {
            "model": {"id": "m1", "name": "Test"},
            "elements": [
                {"id": "app", "type": "ApplicationComponent", "name": "App"},
                {"id": "svc", "type": "ApplicationService", "name": "Svc"},
                {"id": "data", "type": "DataObject", "name": "Data"},
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
                {
                    "id": "r3",
                    "type": "Access",
                    "source": "app",
                    "target": "data",
                },
            ],
            "views": [],
        }
    )

    assert validate_model(model) == []


def test_validate_model_illegal_relationship():
    model = ArchimateModel.model_validate(
        {
            "model": {"id": "m1", "name": "Test"},
            "elements": [
                {"id": "app", "type": "ApplicationComponent", "name": "App"},
                {"id": "svc", "type": "ApplicationService", "name": "Svc"},
            ],
            "relationships": [
                {
                    "id": "r1",
                    "type": "Serving",
                    "source": "app",
                    "target": "svc",
                }
            ],
            "views": [],
        }
    )

    errors = validate_model(model)
    assert any("Illegal relationship" in error for error in errors)
