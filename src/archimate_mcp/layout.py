from __future__ import annotations

from collections import defaultdict

from .grid import build_smart_grid, compute_grid_metrics
from .models import ArchimateModel, Connection, Node, View


# ---------------------------------------------------------------------------
# Layer definitions
# ---------------------------------------------------------------------------

LAYERS: list[dict] = [
    {"id": "business",     "types": ["BusinessActor", "BusinessProcess"]},
    {"id": "application",  "types": ["ApplicationComponent", "ApplicationService", "DataObject"]},
    {"id": "technology",   "types": ["Device", "Node", "SystemSoftware"]},
]

LAYER_IDS = [l["id"] for l in LAYERS]

TYPE_TO_LAYER: dict[str, str] = {
    t: layer["id"] for layer in LAYERS for t in layer["types"]
}

NESTING_TYPES = {"Composition", "Aggregation"}

NODE_W     = 200
NODE_H     = 60
CHILD_W    = 160
CHILD_H    = 50
H_GAP      = 40
LAYER_V_GAP = 160
PADDING    = 20
MARGIN_LEFT = 80
MARGIN_TOP  = 60


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _build_nesting_index(
    model: ArchimateModel,
) -> tuple[dict[str, list[str]], set[str], set[str]]:
    element_by_id = {e.id: e for e in model.elements}
    children_of: dict[str, list[str]] = defaultdict(list)
    nesting_rel_ids: set[str] = set()

    for rel in model.relationships:
        if rel.type not in NESTING_TYPES:
            continue
        src = element_by_id.get(rel.source)
        tgt = element_by_id.get(rel.target)
        if src and tgt and src.type == tgt.type:
            children_of[rel.source].append(rel.target)
            nesting_rel_ids.add(rel.id)

    nested_element_ids: set[str] = {
        cid for kids in children_of.values() for cid in kids
    }
    return children_of, nesting_rel_ids, nested_element_ids


def _node_size(element_id: str, children_of: dict[str, list[str]]) -> tuple[int, int]:
    """Compute (w, h) for a node, accounting for nested children."""
    child_ids = children_of.get(element_id, [])
    if child_ids:
        w = max(NODE_W, len(child_ids) * (CHILD_W + PADDING) + PADDING)
        h = NODE_H + CHILD_H + PADDING * 3
    else:
        w = NODE_W
        h = NODE_H
    return w, h


def _build_child_nodes(
    element_id: str,
    children_of: dict[str, list[str]],
    element_by_id: dict,
    view_id: str,
) -> list[Node]:
    child_nodes: list[Node] = []
    for ci, child_id in enumerate(children_of.get(element_id, [])):
        child_el = element_by_id.get(child_id)
        if not child_el:
            continue
        child_nodes.append(Node(
            id=f"{view_id}_node_{child_id}",
            element_id=child_id,
            x=PADDING + ci * (CHILD_W + PADDING),
            y=PADDING + NODE_H,
            w=CHILD_W,
            h=CHILD_H,
            node_type="Element",
        ))
    return child_nodes


def _build_nodes_from_grid(
    elements: list,
    element_by_id: dict,
    children_of: dict[str, list[str]],
    layer_id: str,
    layer_elements: dict[str, list],
    relationships: list,
    element_layer: dict[str, str],
    layer_order: list[str],
    view_id: str,
) -> tuple[list[Node], dict[str, str]]:
    """
    Use the smart grid to place elements and convert to Node objects.
    Returns (nodes, element_to_node).
    """
    # Compute node sizes for grid metrics
    node_sizes = {
        el.id: _node_size(el.id, children_of)
        for el in elements
    }

    # Build grid for this subset of layers
    grid = build_smart_grid(
        layer_elements=layer_elements,
        layer_order=layer_order,
        relationships=relationships,
        element_layer=element_layer,
    )

    metrics = compute_grid_metrics(
        grid=grid,
        node_sizes=node_sizes,
        h_gap=H_GAP,
        v_gap=LAYER_V_GAP,
        margin_left=MARGIN_LEFT,
        margin_top=MARGIN_TOP,
    )

    nodes: list[Node] = []
    element_to_node: dict[str, str] = {}

    for cell in grid.cells:
        el = element_by_id.get(cell.element_id)
        if not el:
            continue

        w, h = node_sizes[cell.element_id]
        x = metrics.x_of(cell.col)
        y = metrics.y_of(cell.row)

        child_nodes = _build_child_nodes(cell.element_id, children_of, element_by_id, view_id)

        node_id = f"{view_id}_node_{cell.element_id}"
        nodes.append(Node(
            id=node_id,
            element_id=cell.element_id,
            x=x,
            y=y,
            w=w,
            h=h,
            node_type="Element",
            children=child_nodes,
        ))
        element_to_node[cell.element_id] = node_id

        # Also register children
        for child_node in child_nodes:
            element_to_node[child_node.element_id] = child_node.id

    return nodes, element_to_node


def _build_connections(
    model: ArchimateModel,
    element_to_node: dict[str, str],
    nesting_rel_ids: set[str],
    view_id: str,
    rel_type_filter: set[str] | None = None,
) -> list[Connection]:
    connections: list[Connection] = []
    for rel in model.relationships:
        if rel.id in nesting_rel_ids:
            continue
        if rel_type_filter is not None and rel.type not in rel_type_filter:
            continue
        src_node = element_to_node.get(rel.source)
        tgt_node = element_to_node.get(rel.target)
        if src_node and tgt_node:
            connections.append(Connection(
                id=f"{view_id}_conn_{rel.id}",
                relationship_id=rel.id,
                source_node_id=src_node,
                target_node_id=tgt_node,
            ))
    return connections


def _prepare_layer_data(
    model: ArchimateModel,
    nested_element_ids: set[str],
    type_filter: set[str] | None = None,
) -> tuple[dict[str, list], dict[str, str]]:
    """
    Returns:
      layer_elements  — layer_id -> [Element]  (filtered, no nested)
      element_layer   — element_id -> layer_id
    """
    layer_elements: dict[str, list] = defaultdict(list)
    element_layer: dict[str, str] = {}

    for element in model.elements:
        if element.id in nested_element_ids:
            continue
        if type_filter and element.type not in type_filter:
            continue
        lid = TYPE_TO_LAYER.get(element.type, "other")
        layer_elements[lid].append(element)
        element_layer[element.id] = lid

    return layer_elements, element_layer


# ---------------------------------------------------------------------------
# View generators
# ---------------------------------------------------------------------------

def generate_application_view(model: ArchimateModel, view_id: str, view_name: str) -> View:
    """Default layered view — all elements, smart grid layout."""
    element_by_id = {e.id: e for e in model.elements}
    children_of, nesting_rel_ids, nested_element_ids = _build_nesting_index(model)

    layer_elements, element_layer = _prepare_layer_data(model, nested_element_ids)

    nodes, element_to_node = _build_nodes_from_grid(
        elements=model.elements,
        element_by_id=element_by_id,
        children_of=children_of,
        layer_id="all",
        layer_elements=layer_elements,
        relationships=model.relationships,
        element_layer=element_layer,
        layer_order=LAYER_IDS,
        view_id=view_id,
    )

    connections = _build_connections(model, element_to_node, nesting_rel_ids, view_id=view_id)
    return View(id=view_id, name=view_name, nodes=nodes, connections=connections)


def generate_application_cooperation_view(
    model: ArchimateModel, view_id: str, view_name: str
) -> View:
    """Application Cooperation — ApplicationComponents/Services/DataObjects only."""
    TYPES = {"ApplicationComponent", "ApplicationService", "DataObject"}
    REL_TYPES = {"Serving", "Realization", "Access", "Association", "Flow"}

    element_by_id = {e.id: e for e in model.elements}
    children_of, nesting_rel_ids, nested_element_ids = _build_nesting_index(model)

    layer_elements, element_layer = _prepare_layer_data(
        model, nested_element_ids, type_filter=TYPES
    )

    nodes, element_to_node = _build_nodes_from_grid(
        elements=[e for e in model.elements if e.type in TYPES],
        element_by_id=element_by_id,
        children_of=children_of,
        layer_id="application",
        layer_elements=layer_elements,
        relationships=model.relationships,
        element_layer=element_layer,
        layer_order=["application"],
        view_id=view_id,
    )

    connections = _build_connections(
        model, element_to_node, nesting_rel_ids, view_id=view_id, rel_type_filter=REL_TYPES
    )
    return View(id=view_id, name=view_name, nodes=nodes, connections=connections)


def generate_technology_view(
    model: ArchimateModel, view_id: str, view_name: str
) -> View:
    """Technology view — Device/Node/SystemSoftware and structural relationships."""
    TYPES = {"Device", "Node", "SystemSoftware"}
    REL_TYPES = {"Composition", "Aggregation", "Association"}

    element_by_id = {e.id: e for e in model.elements}
    children_of, nesting_rel_ids, nested_element_ids = _build_nesting_index(model)

    layer_elements, element_layer = _prepare_layer_data(
        model, nested_element_ids, type_filter=TYPES
    )

    nodes, element_to_node = _build_nodes_from_grid(
        elements=[e for e in model.elements if e.type in TYPES],
        element_by_id=element_by_id,
        children_of=children_of,
        layer_id="technology",
        layer_elements=layer_elements,
        relationships=model.relationships,
        element_layer=element_layer,
        layer_order=["technology"],
        view_id=view_id,
    )

    connections = _build_connections(
        model, element_to_node, nesting_rel_ids, view_id=view_id, rel_type_filter=REL_TYPES
    )
    return View(id=view_id, name=view_name, nodes=nodes, connections=connections)


def generate_integration_view(
    model: ArchimateModel, view_id: str, view_name: str
) -> View:
    """Integration view — cross-layer elements only, aligned by relationships."""
    INTEGRATION_REL_TYPES = {"Assignment", "Realization", "Serving", "Triggering", "Flow"}

    element_by_id = {e.id: e for e in model.elements}
    children_of, nesting_rel_ids, nested_element_ids = _build_nesting_index(model)

    # Only elements that participate in cross-layer integration relationships
    integration_ids = set()
    for rel in model.relationships:
        if rel.type in INTEGRATION_REL_TYPES:
            src_layer = TYPE_TO_LAYER.get(
                next((e.type for e in model.elements if e.id == rel.source), ""), ""
            )
            tgt_layer = TYPE_TO_LAYER.get(
                next((e.type for e in model.elements if e.id == rel.target), ""), ""
            )
            if src_layer != tgt_layer:
                integration_ids.add(rel.source)
                integration_ids.add(rel.target)

    layer_elements, element_layer = _prepare_layer_data(
        model, nested_element_ids,
        type_filter={e.type for e in model.elements if e.id in integration_ids},
    )
    # Further filter to only integration participants
    for lid in list(layer_elements.keys()):
        layer_elements[lid] = [e for e in layer_elements[lid] if e.id in integration_ids]

    nodes, element_to_node = _build_nodes_from_grid(
        elements=[e for e in model.elements if e.id in integration_ids],
        element_by_id=element_by_id,
        children_of=children_of,
        layer_id="all",
        layer_elements=layer_elements,
        relationships=model.relationships,
        element_layer=element_layer,
        layer_order=LAYER_IDS,
        view_id=view_id,
    )

    connections = _build_connections(
        model, element_to_node, nesting_rel_ids, view_id=view_id, rel_type_filter=INTEGRATION_REL_TYPES
    )
    return View(id=view_id, name=view_name, nodes=nodes, connections=connections)