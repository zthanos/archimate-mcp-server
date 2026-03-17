from __future__ import annotations

import pytest
from pydantic import ValidationError

from archimate_mcp.models import ArchimateModel
from archimate_mcp.validation import validate_model


def test_validate_rejects_unknown_view_node_element_reference() -> None:
    model = ArchimateModel.model_validate(
        {
            "model": {"id": "view-node-ref", "name": "View Node Ref"},
            "elements": [
                {"id": "app_1", "type": "ApplicationComponent", "name": "App A"},
            ],
            "relationships": [],
            "views": [
                {
                    "id": "view_1",
                    "name": "View 1",
                    "nodes": [
                        {
                            "id": "node_1",
                            "element_id": "missing_element",
                            "x": 100,
                            "y": 100,
                            "w": 200,
                            "h": 60,
                            "children": [],
                        }
                    ],
                    "connections": [],
                }
            ],
        }
    )

    errors = validate_model(model)

    assert any(
        "View view_1 references unknown element: missing_element" in err
        for err in errors
    )


def test_validate_rejects_unknown_connection_source_node() -> None:
    model = ArchimateModel.model_validate(
        {
            "model": {"id": "unknown-source-node", "name": "Unknown Source Node"},
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
                }
            ],
            "views": [
                {
                    "id": "view_1",
                    "name": "View 1",
                    "nodes": [
                        {
                            "id": "node_target",
                            "element_id": "svc_1",
                            "x": 100,
                            "y": 100,
                            "w": 200,
                            "h": 60,
                            "children": [],
                        }
                    ],
                    "connections": [
                        {
                            "id": "conn_1",
                            "relationship_id": "rel_1",
                            "source_node_id": "missing_source_node",
                            "target_node_id": "node_target",
                            "bendpoints": [],
                        }
                    ],
                }
            ],
        }
    )

    errors = validate_model(model)

    assert any(
        "View view_1 connection conn_1 unknown source node: missing_source_node" in err
        for err in errors
    )


def test_validate_rejects_unknown_connection_target_node() -> None:
    model = ArchimateModel.model_validate(
        {
            "model": {"id": "unknown-target-node", "name": "Unknown Target Node"},
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
                }
            ],
            "views": [
                {
                    "id": "view_1",
                    "name": "View 1",
                    "nodes": [
                        {
                            "id": "node_source",
                            "element_id": "app_1",
                            "x": 100,
                            "y": 100,
                            "w": 200,
                            "h": 60,
                            "children": [],
                        }
                    ],
                    "connections": [
                        {
                            "id": "conn_1",
                            "relationship_id": "rel_1",
                            "source_node_id": "node_source",
                            "target_node_id": "missing_target_node",
                            "bendpoints": [],
                        }
                    ],
                }
            ],
        }
    )

    errors = validate_model(model)

    assert any(
        "View view_1 connection conn_1 unknown target node: missing_target_node" in err
        for err in errors
    )


def test_model_rejects_invalid_bendpoint_payload() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ArchimateModel.model_validate(
            {
                "model": {"id": "invalid-bendpoint", "name": "Invalid Bendpoint"},
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
                    }
                ],
                "views": [
                    {
                        "id": "view_1",
                        "name": "View 1",
                        "nodes": [
                            {
                                "id": "node_source",
                                "element_id": "app_1",
                                "x": 100,
                                "y": 100,
                                "w": 200,
                                "h": 60,
                                "children": [],
                            },
                            {
                                "id": "node_target",
                                "element_id": "svc_1",
                                "x": 400,
                                "y": 100,
                                "w": 200,
                                "h": 60,
                                "children": [],
                            },
                        ],
                        "connections": [
                            {
                                "id": "conn_1",
                                "relationship_id": "rel_1",
                                "source_node_id": "node_source",
                                "target_node_id": "node_target",
                                "bendpoints": [
                                    {"x": "bad", "y": 100}
                                ],
                            }
                        ],
                    }
                ],
            }
        )

    assert "views.0.connections.0.bendpoints.0.x" in str(exc_info.value)