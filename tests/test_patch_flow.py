from __future__ import annotations

import json
from pathlib import Path

from archimate_mcp.patch import apply_patch
from archimate_mcp.layout import generate_application_view
from archimate_mcp.validation import validate_model
from archimate_mcp.models import ArchimateModel


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_MODEL_PATH = ROOT / "src" / "archimate_mcp" / "examples" / "sample_model.json"


def load_sample_model() -> ArchimateModel:
    data = json.loads(SAMPLE_MODEL_PATH.read_text(encoding="utf-8"))
    return ArchimateModel.model_validate(data)


def test_apply_patch_add_element_and_relationship() -> None:
    model = load_sample_model()

    apply_patch(
        model,
        {
            "action": "add_element",
            "element": {
                "id": "app_patch",
                "type": "ApplicationComponent",
                "name": "Patched App",
            },
        },
    )

    apply_patch(
        model,
        {
            "action": "add_relationship",
            "relationship": {
                "id": "rel_patch",
                "type": "Realization",
                "source": "app_patch",
                "target": "svc_accounts",
            },
        },
    )

    errors = validate_model(model)
    assert errors == []

    view = generate_application_view(model, "patch_view", "Patch View")

    element_ids = {n.element_id for n in view.nodes}
    assert "app_patch" in element_ids