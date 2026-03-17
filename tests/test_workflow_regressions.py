from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

from archimate_mcp.exporter import export_archimate_exchange_xml
from archimate_mcp.layout import generate_application_view, generate_integration_view
from archimate_mcp.models import ArchimateModel, BendPoint, Connection
from archimate_mcp.validation import validate_model


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_MODEL_PATH = ROOT / "src" / "archimate_mcp" / "examples" / "sample_model.json"

NS = {"a": "http://www.opengroup.org/xsd/archimate/3.0/"}


def load_sample_model() -> ArchimateModel:
    data = json.loads(SAMPLE_MODEL_PATH.read_text(encoding="utf-8"))
    return ArchimateModel.model_validate(data)


def build_cross_layer_integration_model() -> ArchimateModel:
    return ArchimateModel.model_validate(
        {
            "model": {
                "id": "integration-test-model",
                "name": "Integration Test Model",
            },
            "elements": [
                {
                    "id": "bp_1",
                    "type": "BusinessProcess",
                    "name": "Customer Onboarding",
                },
                {
                    "id": "app_1",
                    "type": "ApplicationComponent",
                    "name": "Onboarding Service",
                },
            ],
            "relationships": [
                {
                    "id": "rel_flow_1",
                    "type": "Flow",
                    "source": "bp_1",
                    "target": "app_1",
                    "name": "triggers",
                }
            ],
            "views": [],
        }
    )


def test_sample_model_validates() -> None:
    model = load_sample_model()

    errors = validate_model(model)

    assert errors == []


def test_generate_application_view_for_sample_model() -> None:
    model = load_sample_model()

    app_view = generate_application_view(
        model,
        view_id="test_app_view",
        view_name="Application View",
    )

    assert len(app_view.nodes) > 0
    assert len(app_view.connections) > 0


def test_generate_integration_view_for_cross_layer_model() -> None:
    model = build_cross_layer_integration_model()

    integration_view = generate_integration_view(
        model,
        view_id="test_integration_view",
        view_name="Integration View",
    )

    assert len(integration_view.nodes) == 2
    assert len(integration_view.connections) == 1


def test_export_sample_model_to_xml() -> None:
    model = load_sample_model()

    model.views = [
        generate_application_view(
            model,
            view_id="test_app_view",
            view_name="Application View",
        )
    ]

    xml_text = export_archimate_exchange_xml(model)

    assert "<model" in xml_text
    assert "<view" in xml_text
    assert "<node" in xml_text
    assert "<connection" in xml_text

    root = ET.fromstring(xml_text.encode("utf-8"))
    views = root.findall(".//a:view", NS)
    connections = root.findall(".//a:connection", NS)

    assert len(views) >= 1
    assert len(connections) >= 1


def test_export_normalizes_negative_bendpoints() -> None:
    model = load_sample_model()

    view = generate_application_view(
        model,
        view_id="test_negative_coords_view",
        view_name="Negative Coords View",
    )

    assert view.connections, "Expected generated view to contain at least one connection"

    original = view.connections[0]
    view.connections[0] = Connection(
        id=original.id,
        relationship_id=original.relationship_id,
        source_node_id=original.source_node_id,
        target_node_id=original.target_node_id,
        bendpoints=[
            BendPoint(x=-120, y=-80),
            BendPoint(x=40, y=-10),
        ],
    )

    model.views = [view]

    xml_text = export_archimate_exchange_xml(model)
    root = ET.fromstring(xml_text.encode("utf-8"))

    for node in root.findall(".//a:node", NS):
        assert int(node.attrib["x"]) >= 0
        assert int(node.attrib["y"]) >= 0

    for bp in root.findall(".//a:bendpoint", NS):
        assert int(bp.attrib["x"]) >= 0
        assert int(bp.attrib["y"]) >= 0