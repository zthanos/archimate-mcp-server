from __future__ import annotations

from archimate_mcp.models import ArchimateModel, Element, Relationship


def apply_patch(model: ArchimateModel, patch: dict) -> None:
    action = patch.get("action")

    if action == "add_element":
        element = Element(**patch["element"])
        model.elements.append(element)

    elif action == "add_relationship":
        relationship = Relationship(**patch["relationship"])
        model.relationships.append(relationship)

    else:
        raise ValueError(f"Unknown patch action: {action}")