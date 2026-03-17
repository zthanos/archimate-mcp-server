from __future__ import annotations

from collections import defaultdict

from .grid import build_smart_grid, compute_grid_metrics
from .models import ArchimateModel, BendPoint, Connection, Node, View


# ---------------------------------------------------------------------------
# Layer definitions
# ---------------------------------------------------------------------------

LAYERS: list[dict] = [
    {"id": "business", "types": ["BusinessActor", "BusinessProcess"]},
    {
        "id": "application",
        "types": ["ApplicationComponent", "ApplicationService", "DataObject"],
    },
    {"id": "technology", "types": ["Device", "Node", "SystemSoftware"]},
]

LAYER_IDS = [layer["id"] for layer in LAYERS]

TYPE_TO_LAYER: dict[str, str] = {
    element_type: layer["id"] for layer in LAYERS for element_type in layer["types"]
}

NESTING_TYPES = {"Composition", "Aggregation"}

NODE_W = 220
NODE_H = 70
CHILD_W = 170
CHILD_H = 55
H_GAP = 120
LAYER_V_GAP = 240
PADDING = 24
MARGIN_LEFT = 100
MARGIN_TOP = 80

ANCHOR_OFFSET = 16
ROUTE_PADDING = 36
LANE_BASE_OFFSET = 48
LANE_STEP = 24


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
        child_id for child_ids in children_of.values() for child_id in child_ids
    }

    return children_of, nesting_rel_ids, nested_element_ids


def _node_size(element_id: str, children_of: dict[str, list[str]]) -> tuple[int, int]:
    """Compute node size, accounting for nested children."""
    child_ids = children_of.get(element_id, [])
    if child_ids:
        width = max(NODE_W, len(child_ids) * (CHILD_W + PADDING) + PADDING)
        height = NODE_H + CHILD_H + PADDING * 3
    else:
        width = NODE_W
        height = NODE_H
    return width, height


def _build_child_nodes(
    element_id: str,
    children_of: dict[str, list[str]],
    element_by_id: dict,
    view_id: str,
) -> list[Node]:
    child_nodes: list[Node] = []

    for index, child_id in enumerate(children_of.get(element_id, [])):
        child_el = element_by_id.get(child_id)
        if not child_el:
            continue

        child_nodes.append(
            Node(
                id=f"{view_id}_node_{child_id}",
                element_id=child_id,
                x=PADDING + index * (CHILD_W + PADDING),
                y=PADDING + NODE_H,
                w=CHILD_W,
                h=CHILD_H,
                node_type="Element",
            )
        )

    return child_nodes


def _center_x(node: Node) -> int:
    return node.x + node.w // 2


def _center_y(node: Node) -> int:
    return node.y + node.h // 2


def _left(node: Node) -> int:
    return node.x


def _right(node: Node) -> int:
    return node.x + node.w


def _top(node: Node) -> int:
    return node.y


def _bottom(node: Node) -> int:
    return node.y + node.h


def _segment_intersects_rect(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    node: Node,
    padding: int = ROUTE_PADDING,
) -> bool:
    """
    Axis-aligned segment vs expanded rectangle.
    Only horizontal or vertical segments are supported.
    """
    left = node.x - padding
    right = node.x + node.w + padding
    top = node.y - padding
    bottom = node.y + node.h + padding

    if x1 == x2:
        x = x1
        seg_top = min(y1, y2)
        seg_bottom = max(y1, y2)

        if not (left <= x <= right):
            return False

        return not (seg_bottom < top or seg_top > bottom)

    if y1 == y2:
        y = y1
        seg_left = min(x1, x2)
        seg_right = max(x1, x2)

        if not (top <= y <= bottom):
            return False

        return not (seg_right < left or seg_left > right)

    return False


def _polyline_intersects_any_node(
    points: list[tuple[int, int]],
    obstacle_nodes: list[Node],
    source_id: str,
    target_id: str,
) -> bool:
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]

        for node in obstacle_nodes:
            if node.id in (source_id, target_id):
                continue

            if _segment_intersects_rect(x1, y1, x2, y2, node):
                return True

    return False


def _dedupe_points(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not points:
        return points

    result = [points[0]]
    for point in points[1:]:
        if point != result[-1]:
            result.append(point)

    return result


def _remove_collinear_middle_points(
    points: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    if len(points) <= 2:
        return points

    simplified = [points[0]]

    for i in range(1, len(points) - 1):
        prev_x, prev_y = simplified[-1]
        curr_x, curr_y = points[i]
        next_x, next_y = points[i + 1]

        same_vertical = prev_x == curr_x == next_x
        same_horizontal = prev_y == curr_y == next_y

        if same_vertical or same_horizontal:
            continue

        simplified.append((curr_x, curr_y))

    simplified.append(points[-1])
    return simplified


def _normalize_points(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return _remove_collinear_middle_points(_dedupe_points(points))


def _points_to_bendpoints(points: list[tuple[int, int]]) -> list[BendPoint]:
    if len(points) <= 2:
        return []

    middle_points = points[1:-1]
    return [BendPoint(x=x, y=y) for x, y in middle_points]


def _lane_offset(source_id: str, target_id: str) -> int:
    seed = sum(ord(ch) for ch in f"{source_id}|{target_id}")
    return LANE_BASE_OFFSET + (seed % 3) * LANE_STEP


def _path_is_clear(
    points: list[tuple[int, int]],
    obstacle_nodes: list[Node],
    source_id: str,
    target_id: str,
) -> bool:
    normalized = _normalize_points(points)
    return not _polyline_intersects_any_node(
        normalized,
        obstacle_nodes,
        source_id,
        target_id,
    )


def _find_free_horizontal_lane(
    source: Node,
    target: Node,
    start: tuple[int, int],
    end: tuple[int, int],
    obstacle_nodes: list[Node],
    lane_offset: int,
    max_tries: int = 12,
) -> list[tuple[int, int]] | None:
    """
    Try progressively wider top/bottom lanes until a collision-free route is found.
    """
    top_base = min(_top(source), _top(target))
    bottom_base = max(_bottom(source), _bottom(target))

    if end[0] >= start[0]:
        out_x = start[0] + lane_offset
        in_x = end[0] - lane_offset
    else:
        out_x = start[0] - lane_offset
        in_x = end[0] + lane_offset

    for i in range(max_tries):
        extra = lane_offset + i * LANE_STEP

        top_lane = top_base - extra
        candidate_top = [
            start,
            (out_x, start[1]),
            (out_x, top_lane),
            (in_x, top_lane),
            (in_x, end[1]),
            end,
        ]
        if _path_is_clear(candidate_top, obstacle_nodes, source.id, target.id):
            return _normalize_points(candidate_top)

        bottom_lane = bottom_base + extra
        candidate_bottom = [
            start,
            (out_x, start[1]),
            (out_x, bottom_lane),
            (in_x, bottom_lane),
            (in_x, end[1]),
            end,
        ]
        if _path_is_clear(candidate_bottom, obstacle_nodes, source.id, target.id):
            return _normalize_points(candidate_bottom)

    return None


def _find_free_vertical_lane(
    source: Node,
    target: Node,
    start: tuple[int, int],
    end: tuple[int, int],
    obstacle_nodes: list[Node],
    lane_offset: int,
    max_tries: int = 12,
) -> list[tuple[int, int]] | None:
    """
    Try progressively wider left/right lanes until a collision-free route is found.
    """
    left_base = min(_left(source), _left(target))
    right_base = max(_right(source), _right(target))

    for i in range(max_tries):
        extra = lane_offset + i * LANE_STEP

        left_lane = left_base - extra
        candidate_left = [
            start,
            (left_lane, start[1]),
            (left_lane, end[1]),
            end,
        ]
        if _path_is_clear(candidate_left, obstacle_nodes, source.id, target.id):
            return _normalize_points(candidate_left)

        right_lane = right_base + extra
        candidate_right = [
            start,
            (right_lane, start[1]),
            (right_lane, end[1]),
            end,
        ]
        if _path_is_clear(candidate_right, obstacle_nodes, source.id, target.id):
            return _normalize_points(candidate_right)

    return None


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


def _build_pair_route_order(
    model: ArchimateModel,
    element_to_node: dict[str, str],
    nesting_rel_ids: set[str],
    rel_type_filter: set[str] | None = None,
) -> dict[str, tuple[int, int, int]]:
    """
    Returns:
      relationship_id -> (pair_index, pair_count, direction)

    direction:
      1  => canonical direction
      -1 => reverse direction
    """
    grouped: dict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)

    for rel in model.relationships:
        if rel.id in nesting_rel_ids:
            continue
        if rel_type_filter is not None and rel.type not in rel_type_filter:
            continue

        src_node_id = element_to_node.get(rel.source)
        tgt_node_id = element_to_node.get(rel.target)
        if not src_node_id or not tgt_node_id:
            continue

        key = _pair_key(src_node_id, tgt_node_id)
        grouped[key].append((rel.id, src_node_id, tgt_node_id))

    result: dict[str, tuple[int, int, int]] = {}

    for key, items in grouped.items():
        canonical_a, canonical_b = key
        count = len(items)

        # stable ordering
        items = sorted(items, key=lambda x: x[0])

        for idx, (rel_id, src_node_id, tgt_node_id) in enumerate(items):
            direction = (
                1 if (src_node_id, tgt_node_id) == (canonical_a, canonical_b) else -1
            )
            result[rel_id] = (idx, count, direction)

    return result


def _lane_band(pair_index: int, direction: int) -> tuple[str, int]:
    """
    Alternate above/below (or left/right) and expand outward.
    pair_index=0 -> near band
    pair_index=1 -> opposite near band
    pair_index=2 -> further same side
    pair_index=3 -> further opposite side
    """
    level = pair_index // 2
    parity = pair_index % 2

    if direction == 1:
        side = "top" if parity == 0 else "bottom"
    else:
        side = "bottom" if parity == 0 else "top"

    return side, level


def _try_minimal_route(
    source: Node,
    target: Node,
    obstacle_nodes: list[Node],
) -> list[tuple[int, int]] | None:
    sx = _center_x(source)
    sy = _center_y(source)
    tx = _center_x(target)
    ty = _center_y(target)

    if tx >= sx:
        start = (_right(source) + ANCHOR_OFFSET, sy)
        end = (_left(target) - ANCHOR_OFFSET, ty)
    else:
        start = (_left(source) - ANCHOR_OFFSET, sy)
        end = (_right(target) + ANCHOR_OFFSET, ty)

    candidates: list[list[tuple[int, int]]] = []

    if start[1] == end[1]:
        candidates.append([start, end])

    if start[0] == end[0]:
        candidates.append([start, end])

    candidates.append([start, (end[0], start[1]), end])
    candidates.append([start, (start[0], end[1]), end])

    for candidate in candidates:
        normalized = _normalize_points(candidate)
        if not _polyline_intersects_any_node(
            normalized,
            obstacle_nodes,
            source.id,
            target.id,
        ):
            return normalized

    return None

def _route_connection(
    source: Node,
    target: Node,
    obstacle_nodes: list[Node],
    pair_index: int = 0,
    pair_count: int = 1,
    direction: int = 1,
) -> list[BendPoint]:
    # 1. Single relationship between the pair -> prefer minimal clean route
    if pair_count == 1:
        minimal = _try_minimal_route(source, target, obstacle_nodes)
        if minimal is not None:
            return _points_to_bendpoints(minimal)

    sx = _center_x(source)
    sy = _center_y(source)
    tx = _center_x(target)
    ty = _center_y(target)

    if tx >= sx:
        start = (_right(source) + ANCHOR_OFFSET, sy)
        end = (_left(target) - ANCHOR_OFFSET, ty)
        x_dir = 1
    else:
        start = (_left(source) - ANCHOR_OFFSET, sy)
        end = (_right(target) + ANCHOR_OFFSET, ty)
        x_dir = -1

    spread = pair_index // 2
    lane_extra = LANE_BASE_OFFSET + spread * LANE_STEP

    side = "top" if (pair_index + (0 if direction == 1 else 1)) % 2 == 0 else "bottom"

    top_lane = min(_top(source), _top(target)) - lane_extra
    bottom_lane = max(_bottom(source), _bottom(target)) + lane_extra

    out_x = start[0] + (x_dir * lane_extra)
    in_x = end[0] - (x_dir * lane_extra)

    candidates: list[list[tuple[int, int]]] = []

    if side == "top":
        candidates.append([
            start,
            (out_x, start[1]),
            (out_x, top_lane),
            (in_x, top_lane),
            (in_x, end[1]),
            end,
        ])
        candidates.append([
            start,
            (out_x, start[1]),
            (out_x, bottom_lane),
            (in_x, bottom_lane),
            (in_x, end[1]),
            end,
        ])
    else:
        candidates.append([
            start,
            (out_x, start[1]),
            (out_x, bottom_lane),
            (in_x, bottom_lane),
            (in_x, end[1]),
            end,
        ])
        candidates.append([
            start,
            (out_x, start[1]),
            (out_x, top_lane),
            (in_x, top_lane),
            (in_x, end[1]),
            end,
        ])

    # 2. For multi-rel pairs, only after pair split routing try minimal doglegs
    hv = _normalize_points([start, (end[0], start[1]), end])
    vh = _normalize_points([start, (start[0], end[1]), end])

    candidates.append(hv)
    candidates.append(vh)

    for candidate in candidates:
        normalized = _normalize_points(candidate)
        if not _polyline_intersects_any_node(
            normalized,
            obstacle_nodes,
            source.id,
            target.id,
        ):
            return _points_to_bendpoints(normalized)

    # 3. Last fallback
    fallback = _normalize_points(candidates[0])
    return _points_to_bendpoints(fallback)

def _build_connections_with_routing(
    model: ArchimateModel,
    element_to_node: dict[str, str],
    node_by_id: dict[str, Node],
    top_level_nodes: list[Node],
    nesting_rel_ids: set[str],
    view_id: str,
    rel_type_filter: set[str] | None = None,
) -> list[Connection]:
    connections: list[Connection] = []

    pair_route_order = _build_pair_route_order(
        model,
        element_to_node,
        nesting_rel_ids,
        rel_type_filter=rel_type_filter,
    )

    for rel in model.relationships:
        if rel.id in nesting_rel_ids:
            continue
        if rel_type_filter is not None and rel.type not in rel_type_filter:
            continue

        src_node_id = element_to_node.get(rel.source)
        tgt_node_id = element_to_node.get(rel.target)
        if not src_node_id or not tgt_node_id:
            continue

        src_node = node_by_id.get(src_node_id)
        tgt_node = node_by_id.get(tgt_node_id)
        if not src_node or not tgt_node:
            continue

        pair_index, pair_count, direction = pair_route_order.get(rel.id, (0, 1, 1))

        bendpoints = _route_connection(
            src_node,
            tgt_node,
            top_level_nodes,
            pair_index=pair_index,
            pair_count=pair_count,
            direction=direction,
        )

        connections.append(
            Connection(
                id=f"{view_id}_conn_{rel.id}",
                relationship_id=rel.id,
                source_node_id=src_node_id,
                target_node_id=tgt_node_id,
                bendpoints=bendpoints,
            )
        )

    return connections


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
) -> tuple[list[Node], dict[str, str], dict[str, Node]]:
    """
    Use the smart grid to place elements and convert them to Nodes.

    Returns:
      nodes, element_to_node, node_by_id
    """
    del layer_id  # kept for compatibility with current calling pattern

    node_sizes = {
        element.id: _node_size(element.id, children_of) for element in elements
    }

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
    node_by_id: dict[str, Node] = {}

    for cell in grid.cells:
        element = element_by_id.get(cell.element_id)
        if not element:
            continue

        width, height = node_sizes[cell.element_id]
        x = metrics.x_of(cell.col)
        y = metrics.y_of(cell.row)

        child_nodes = _build_child_nodes(
            cell.element_id,
            children_of,
            element_by_id,
            view_id,
        )

        node_id = f"{view_id}_node_{cell.element_id}"
        node = Node(
            id=node_id,
            element_id=cell.element_id,
            x=x,
            y=y,
            w=width,
            h=height,
            node_type="Element",
            children=child_nodes,
        )

        nodes.append(node)
        node_by_id[node_id] = node
        element_to_node[cell.element_id] = node_id

        for child_node in child_nodes:
            if child_node.element_id is not None:
                element_to_node[child_node.element_id] = child_node.id
            node_by_id[child_node.id] = child_node

    return nodes, element_to_node, node_by_id


def _build_connections(
    model: ArchimateModel,
    element_to_node: dict[str, str],
    nesting_rel_ids: set[str],
    view_id: str,
    rel_type_filter: set[str] | None = None,
) -> list[Connection]:
    """
    Basic connection builder without routing.
    Left in place as a fallback utility.
    """
    connections: list[Connection] = []

    for rel in model.relationships:
        if rel.id in nesting_rel_ids:
            continue
        if rel_type_filter is not None and rel.type not in rel_type_filter:
            continue

        src_node_id = element_to_node.get(rel.source)
        tgt_node_id = element_to_node.get(rel.target)

        if src_node_id and tgt_node_id:
            connections.append(
                Connection(
                    id=f"{view_id}_conn_{rel.id}",
                    relationship_id=rel.id,
                    source_node_id=src_node_id,
                    target_node_id=tgt_node_id,
                )
            )

    return connections


def _prepare_layer_data(
    model: ArchimateModel,
    nested_element_ids: set[str],
    type_filter: set[str] | None = None,
) -> tuple[dict[str, list], dict[str, str]]:
    """
    Returns:
      layer_elements: layer_id -> [Element]  (filtered, excluding nested)
      element_layer:  element_id -> layer_id
    """
    layer_elements: dict[str, list] = defaultdict(list)
    element_layer: dict[str, str] = {}

    for element in model.elements:
        if element.id in nested_element_ids:
            continue
        if type_filter is not None and element.type not in type_filter:
            continue

        layer_id = TYPE_TO_LAYER.get(element.type, "other")
        layer_elements[layer_id].append(element)
        element_layer[element.id] = layer_id

    return layer_elements, element_layer


# ---------------------------------------------------------------------------
# View generators
# ---------------------------------------------------------------------------


def generate_application_view(
    model: ArchimateModel,
    view_id: str,
    view_name: str,
) -> View:
    element_by_id = {e.id: e for e in model.elements}
    children_of, nesting_rel_ids, nested_element_ids = _build_nesting_index(model)

    layer_elements, element_layer = _prepare_layer_data(model, nested_element_ids)

    nodes, element_to_node, node_by_id = _build_nodes_from_grid(
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

    connections = _build_connections_with_routing(
        model,
        element_to_node,
        node_by_id,
        nodes,
        nesting_rel_ids,
        view_id=view_id,
    )

    return View(
        id=view_id,
        name=view_name,
        nodes=nodes,
        connections=connections,
    )


def generate_application_cooperation_view(
    model: ArchimateModel,
    view_id: str,
    view_name: str,
) -> View:
    types = {"ApplicationComponent", "ApplicationService", "DataObject"}
    rel_types = {"Serving", "Realization", "Access", "Association", "Flow"}

    element_by_id = {e.id: e for e in model.elements}
    children_of, nesting_rel_ids, nested_element_ids = _build_nesting_index(model)

    layer_elements, element_layer = _prepare_layer_data(
        model,
        nested_element_ids,
        type_filter=types,
    )

    nodes, element_to_node, node_by_id = _build_nodes_from_grid(
        elements=[e for e in model.elements if e.type in types],
        element_by_id=element_by_id,
        children_of=children_of,
        layer_id="application",
        layer_elements=layer_elements,
        relationships=model.relationships,
        element_layer=element_layer,
        layer_order=["application"],
        view_id=view_id,
    )

    connections = _build_connections_with_routing(
        model=model,
        element_to_node=element_to_node,
        node_by_id=node_by_id,
        top_level_nodes=nodes,
        nesting_rel_ids=nesting_rel_ids,
        view_id=view_id,
        rel_type_filter=rel_types,
    )

    return View(
        id=view_id,
        name=view_name,
        nodes=nodes,
        connections=connections,
    )


def generate_technology_view(
    model: ArchimateModel,
    view_id: str,
    view_name: str,
) -> View:
    types = {"Device", "Node", "SystemSoftware"}
    rel_types = {"Composition", "Aggregation", "Association"}

    element_by_id = {e.id: e for e in model.elements}
    children_of, nesting_rel_ids, nested_element_ids = _build_nesting_index(model)

    layer_elements, element_layer = _prepare_layer_data(
        model,
        nested_element_ids,
        type_filter=types,
    )

    nodes, element_to_node, node_by_id = _build_nodes_from_grid(
        elements=[e for e in model.elements if e.type in types],
        element_by_id=element_by_id,
        children_of=children_of,
        layer_id="technology",
        layer_elements=layer_elements,
        relationships=model.relationships,
        element_layer=element_layer,
        layer_order=["technology"],
        view_id=view_id,
    )

    connections = _build_connections_with_routing(
        model=model,
        element_to_node=element_to_node,
        node_by_id=node_by_id,
        top_level_nodes=nodes,
        nesting_rel_ids=nesting_rel_ids,
        view_id=view_id,
        rel_type_filter=rel_types,
    )

    return View(
        id=view_id,
        name=view_name,
        nodes=nodes,
        connections=connections,
    )


def generate_integration_view(
    model: ArchimateModel,
    view_id: str,
    view_name: str,
) -> View:
    """
    Integration view:
    shows only elements participating in cross-layer integration relationships.
    """
    integration_rel_types = {
        "Assignment",
        "Realization",
        "Serving",
        "Triggering",
        "Flow",
    }

    element_by_id = {e.id: e for e in model.elements}
    children_of, nesting_rel_ids, nested_element_ids = _build_nesting_index(model)

    model_element_map = {e.id: e for e in model.elements}

    integration_ids: set[str] = set()

    for rel in model.relationships:
        if rel.type not in integration_rel_types:
            continue

        src_el = model_element_map.get(rel.source)
        tgt_el = model_element_map.get(rel.target)
        if not src_el or not tgt_el:
            continue

        src_layer = TYPE_TO_LAYER.get(src_el.type, "")
        tgt_layer = TYPE_TO_LAYER.get(tgt_el.type, "")

        if src_layer != tgt_layer:
            integration_ids.add(rel.source)
            integration_ids.add(rel.target)

    integration_types = {e.type for e in model.elements if e.id in integration_ids}

    layer_elements, element_layer = _prepare_layer_data(
        model,
        nested_element_ids,
        type_filter=integration_types,
    )

    for layer_id in list(layer_elements.keys()):
        layer_elements[layer_id] = [
            element
            for element in layer_elements[layer_id]
            if element.id in integration_ids
        ]

    nodes, element_to_node, node_by_id = _build_nodes_from_grid(
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

    connections = _build_connections_with_routing(
        model=model,
        element_to_node=element_to_node,
        node_by_id=node_by_id,
        top_level_nodes=nodes,
        nesting_rel_ids=nesting_rel_ids,
        view_id=view_id,
        rel_type_filter=integration_rel_types,
    )

    return View(
        id=view_id,
        name=view_name,
        nodes=nodes,
        connections=connections,
    )
