from __future__ import annotations

from .models import ArchimateModel


ALLOWED_RELATIONSHIPS: set[tuple[str, str, str]] = {
    # ---------------------------------------------------------------------------
    # Business layer
    # ---------------------------------------------------------------------------
    ("BusinessActor",   "Assignment",   "BusinessProcess"),
    ("BusinessActor",   "Assignment",   "BusinessActor"),
    ("BusinessActor",   "Association",  "BusinessActor"),
    ("BusinessActor",   "Association",  "BusinessProcess"),
    ("BusinessProcess", "Triggering",   "BusinessProcess"),
    ("BusinessProcess", "Flow",         "BusinessProcess"),
    ("BusinessProcess", "Association",  "BusinessProcess"),
    ("BusinessProcess", "Composition",  "BusinessProcess"),
    ("BusinessProcess", "Aggregation",  "BusinessProcess"),

    # ---------------------------------------------------------------------------
    # Application layer — components
    # ---------------------------------------------------------------------------
    ("ApplicationComponent", "Composition",  "ApplicationComponent"),
    ("ApplicationComponent", "Aggregation",  "ApplicationComponent"),
    ("ApplicationComponent", "Association",  "ApplicationComponent"),
    ("ApplicationComponent", "Flow",         "ApplicationComponent"),
    ("ApplicationComponent", "Realization",  "ApplicationService"),
    ("ApplicationComponent", "Access",       "DataObject"),
    ("ApplicationComponent", "Serving",      "ApplicationComponent"),
    ("ApplicationComponent", "Serving",      "BusinessProcess"),
    ("ApplicationComponent", "Serving",      "BusinessActor"),

    # Application layer — services
    ("ApplicationService",   "Serving",      "ApplicationComponent"),
    ("ApplicationService",   "Serving",      "BusinessProcess"),
    ("ApplicationService",   "Serving",      "BusinessActor"),
    ("ApplicationService",   "Association",  "ApplicationService"),
    ("ApplicationService",   "Flow",         "ApplicationService"),
    ("ApplicationService",   "Access",       "DataObject"),

    # Application layer — data
    ("DataObject",           "Association",  "DataObject"),
    ("DataObject",           "Composition",  "DataObject"),
    ("DataObject",           "Aggregation",  "DataObject"),

    # ---------------------------------------------------------------------------
    # Technology layer — devices
    # ---------------------------------------------------------------------------
    ("Device",           "Composition",  "Device"),
    ("Device",           "Aggregation",  "Device"),
    ("Device",           "Association",  "Device"),
    ("Device",           "Composition",  "Node"),
    ("Device",           "Aggregation",  "Node"),
    ("Device",           "Composition",  "SystemSoftware"),
    ("Device",           "Serving",      "Device"),
    ("Device",           "Serving",      "ApplicationComponent"),

    # Technology layer — nodes
    ("Node",             "Composition",  "Node"),
    ("Node",             "Aggregation",  "Node"),
    ("Node",             "Association",  "Node"),
    ("Node",             "Composition",  "SystemSoftware"),
    ("Node",             "Aggregation",  "SystemSoftware"),
    ("Node",             "Composition",  "ApplicationComponent"),   # deployment
    ("Node",             "Serving",      "ApplicationComponent"),
    ("Node",             "Serving",      "Node"),

    # Technology layer — system software
    ("SystemSoftware",   "Composition",  "SystemSoftware"),
    ("SystemSoftware",   "Aggregation",  "SystemSoftware"),
    ("SystemSoftware",   "Association",  "SystemSoftware"),
    ("SystemSoftware",   "Composition",  "ApplicationComponent"),
    ("SystemSoftware",   "Serving",      "ApplicationComponent"),
    ("SystemSoftware",   "Serving",      "SystemSoftware"),

    # ---------------------------------------------------------------------------
    # Cross-layer
    # ---------------------------------------------------------------------------
    ("ApplicationComponent", "Realization",  "BusinessProcess"),
    ("ApplicationService",   "Realization",  "BusinessProcess"),
    ("Node",                 "Realization",  "ApplicationComponent"),
    ("SystemSoftware",       "Realization",  "ApplicationComponent"),
    ("Device",               "Realization",  "ApplicationComponent"),
}


class ValidationError(Exception):
    pass


def validate_model(model: ArchimateModel) -> list[str]:
    errors: list[str] = []

    element_ids: set[str] = set()
    relationship_ids: set[str] = set()
    view_ids: set[str] = set()

    element_map = {}

    for element in model.elements:
        if element.id in element_ids:
            errors.append(f"Duplicate element id: {element.id}")
        element_ids.add(element.id)
        element_map[element.id] = element

    for relationship in model.relationships:
        if relationship.id in relationship_ids:
            errors.append(f"Duplicate relationship id: {relationship.id}")
        relationship_ids.add(relationship.id)

        if relationship.source not in element_map:
            errors.append(
                f"Relationship {relationship.id} source not found: {relationship.source}"
            )
        if relationship.target not in element_map:
            errors.append(
                f"Relationship {relationship.id} target not found: {relationship.target}"
            )

        if relationship.source in element_map and relationship.target in element_map:
            source_type = element_map[relationship.source].type
            target_type = element_map[relationship.target].type
            triple = (source_type, relationship.type, target_type)
            if triple not in ALLOWED_RELATIONSHIPS:
                errors.append(
                    f"Illegal relationship {relationship.id}: "
                    f"{source_type} -[{relationship.type}]-> {target_type}"
                )

    for view in model.views:
        if view.id in view_ids:
            errors.append(f"Duplicate view id: {view.id}")
        view_ids.add(view.id)

        node_ids: set[str] = set()
        for node in view.nodes:
            if node.id in node_ids:
                errors.append(f"Duplicate node id in view {view.id}: {node.id}")
            node_ids.add(node.id)

            if node.element_id not in element_map:
                errors.append(
                    f"View {view.id} references unknown element: {node.element_id}"
                )

            if node.w <= 0 or node.h <= 0:
                errors.append(f"View {view.id} node {node.id} has invalid size")

        for connection in view.connections:
            if connection.relationship_id not in relationship_ids:
                errors.append(
                    f"View {view.id} connection {connection.id} unknown relationship: "
                    f"{connection.relationship_id}"
                )
            if connection.source_node_id not in node_ids:
                errors.append(
                    f"View {view.id} connection {connection.id} unknown source node: "
                    f"{connection.source_node_id}"
                )
            if connection.target_node_id not in node_ids:
                errors.append(
                    f"View {view.id} connection {connection.id} unknown target node: "
                    f"{connection.target_node_id}"
                )

    return errors