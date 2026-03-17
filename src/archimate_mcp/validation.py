from __future__ import annotations

from .models import ArchimateModel, Node


ALLOWED_RELATIONSHIPS: set[tuple[str, str, str]] = {
    ("ApplicationService", "Serving", "ApplicationComponent"),
    ("ApplicationComponent", "Access", "DataObject"),
    ("BusinessActor", "Assignment", "BusinessProcess"),
    ("ApplicationComponent", "Composition", "ApplicationComponent"),
    ("ApplicationComponent", "Aggregation", "ApplicationComponent"),
    ("ApplicationComponent", "Association", "ApplicationComponent"),
    ("ApplicationComponent", "Flow", "ApplicationComponent"),
    ("BusinessProcess", "Triggering", "BusinessProcess"),
    ("ApplicationComponent", "Realization", "ApplicationService"),
    ("Node", "Composition", "SystemSoftware"),
    ("SystemSoftware", "Composition", "ApplicationComponent"),
    ("Device", "Composition", "Node"),
}


class ValidationError(Exception):
    pass


def _collect_node_ids(nodes: list[Node], result: set[str]) -> None:
    """Recursively collect all node ids, including nested children."""
    for node in nodes:
        result.add(node.id)
        if node.children:
            _collect_node_ids(node.children, result)


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

        # Collect all node ids recursively (handles nested/container nodes)
        node_ids: set[str] = set()
        _collect_node_ids(view.nodes, node_ids)

        # Validate each node recursively
        def _validate_nodes(nodes: list[Node]) -> None:
            for node in nodes:
                # Skip container nodes (element_id is None)
                if node.element_id is not None and node.element_id not in element_map:
                    errors.append(
                        f"View {view.id} references unknown element: {node.element_id}"
                    )
                if node.w <= 0 or node.h <= 0:
                    errors.append(f"View {view.id} node {node.id} has invalid size")
                if node.children:
                    _validate_nodes(node.children)

        _validate_nodes(view.nodes)

        for connection in view.connections:
            for bp in connection.bendpoints:
                if not isinstance(bp.x, int) or not isinstance(bp.y, int):
                    errors.append(
                        f"View {view.id} connection {connection.id} has invalid bendpoint"
                    )
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