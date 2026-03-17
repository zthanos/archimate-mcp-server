from __future__ import annotations

from archimate_mcp.models import ArchimateModel
from archimate_mcp.validation import validate_model


def test_validate_rejects_duplicate_element_ids() -> None:
    model = ArchimateModel.model_validate(
        {
            "model": {"id": "dup-elements", "name": "Duplicate Elements"},
            "elements": [
                {"id": "app_1", "type": "ApplicationComponent", "name": "App A"},
                {"id": "app_1", "type": "ApplicationComponent", "name": "App B"},
            ],
            "relationships": [],
            "views": [],
        }
    )

    errors = validate_model(model)

    assert any("Duplicate element id: app_1" in err for err in errors)


def test_validate_rejects_duplicate_relationship_ids() -> None:
    model = ArchimateModel.model_validate(
        {
            "model": {"id": "dup-relationships", "name": "Duplicate Relationships"},
            "elements": [
                {"id": "app_1", "type": "ApplicationComponent", "name": "App A"},
                {"id": "svc_1", "type": "ApplicationService", "name": "Service A"},
            ],
            "relationships": [
                {
                    "id": "rel_1",
                    "type": "Realization",
                    "source": "app_1",
                    "target": "svc_1",
                },
                {
                    "id": "rel_1",
                    "type": "Realization",
                    "source": "app_1",
                    "target": "svc_1",
                },
            ],
            "views": [],
        }
    )

    errors = validate_model(model)

    assert any("Duplicate relationship id: rel_1" in err for err in errors)


def test_validate_rejects_illegal_relationship_triple() -> None:
    model = ArchimateModel.model_validate(
        {
            "model": {"id": "illegal-rel", "name": "Illegal Relationship"},
            "elements": [
                {"id": "actor_1", "type": "BusinessActor", "name": "Customer"},
                {"id": "svc_1", "type": "ApplicationService", "name": "Account Service"},
            ],
            "relationships": [
                {
                    "id": "rel_1",
                    "type": "Realization",
                    "source": "actor_1",
                    "target": "svc_1",
                }
            ],
            "views": [],
        }
    )

    errors = validate_model(model)

    assert any(
        "Illegal relationship rel_1: BusinessActor -[Realization]-> ApplicationService" in err
        for err in errors
    )


def test_validate_rejects_unknown_relationship_source_and_target() -> None:
    model = ArchimateModel.model_validate(
        {
            "model": {"id": "unknown-ref", "name": "Unknown Reference"},
            "elements": [
                {"id": "app_1", "type": "ApplicationComponent", "name": "App A"},
                {"id": "svc_1", "type": "ApplicationService", "name": "Service A"},
            ],
            "relationships": [
                {
                    "id": "rel_1",
                    "type": "Realization",
                    "source": "missing_source",
                    "target": "missing_target",
                }
            ],
            "views": [],
        }
    )

    errors = validate_model(model)

    assert any(
        "Relationship rel_1 source not found: missing_source" in err
        for err in errors
    )
    assert any(
        "Relationship rel_1 target not found: missing_target" in err
        for err in errors
    )