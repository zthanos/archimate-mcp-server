from __future__ import annotations

import json
from pathlib import Path

from archimate_mcp.exporter import export_archimate_exchange_xml
from archimate_mcp.layout import generate_application_view
from archimate_mcp.models import ArchimateModel, Element, Relationship
from archimate_mcp.validation import validate_model


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_MODEL_PATH = ROOT / "src" / "archimate_mcp" / "examples" / "sample_model.json"


def load_sample_model() -> ArchimateModel:
    data = json.loads(SAMPLE_MODEL_PATH.read_text(encoding="utf-8"))
    return ArchimateModel.model_validate(data)


def test_add_element_and_regenerate_views_flow() -> None:
    model = load_sample_model()

    new_element = Element(
        id="app_new",
        type="ApplicationComponent",
        name="New App Component",
    )
    model.elements.append(new_element)

    new_relationship = Relationship(
        id="rel_new",
        type="Realization",
        source="app_new",
        target="svc_accounts",
        name="implements",
    )
    model.relationships.append(new_relationship)

    errors = validate_model(model)
    assert errors == []

    view = generate_application_view(
        model,
        view_id="updated_view",
        view_name="Updated View",
    )

    model.views = [view]

    element_ids_in_view = {node.element_id for node in view.nodes}
    assert "app_new" in element_ids_in_view

    relationship_ids_in_view = {conn.relationship_id for conn in view.connections}
    assert "rel_new" in relationship_ids_in_view

    xml = export_archimate_exchange_xml(model)

    assert "<model" in xml
    assert "app_new" in xml
    assert "rel_new" in xml