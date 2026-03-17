from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from .config import DEFAULT_CONFIG, LayoutConfig
from .grid import build_smart_grid, compute_grid_metrics
from .models import ArchimateModel, BendPoint, Connection, Element, Node, View

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Layer definitions
# ---------------------------------------------------------------------------

LAYERS: list[dict[str, str | list[str]]] = [
    {"id": "business",    "types": ["BusinessActor", "BusinessProcess"]},
    {"id": "application", "types": ["ApplicationComponent", "ApplicationService", "DataObject"]},
    {"id": "technology",  "types": ["Device", "Node", "SystemSoftware"]},
]

LAYER_IDS: list[str] = [str(layer["id"]) for layer in LAYERS]

TYPE_TO_LAYER: dict[str, str] = {
    element_type: str(layer["id"])
    for layer in LAYERS
    for element_type in layer["types"]  # type: ignore[union-attr]
}

NESTING_TYPES: frozenset[str] = frozenset({"Composition", "Aggregation"})


# ---------------------------------------------------------------------------
# Node geometry helpers
# ---------------------------------------------------------------------------

def _cx(node: Node) -> int: return node.x + node.w // 2
def _cy(node: Node) -> int: return node.y + node.h // 2
def _left(node: Node) -> int: return node.x
def _right(node: Node) -> int: return node.x + node.w
def _top(node: Node) -> int: return node.y
def _bottom(node: Node) -> int: return node.y + node.h


# ---------------------------------------------------------------------------
# Polyline helpers
# ---------------------------------------------------------------------------

def _dedupe_points(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not points:
        return points
    result = [points[0]]
    for pt in points[1:]:
        if pt != result[-1]:
            result.append(pt)
    return result


def _remove_collinear(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if len(points) <= 2:
        return points
    simplified = [points[0]]
    for i in range(1, len(points) - 1):
        px, py = simplified[-1]
        cx, cy = points[i]
        nx, ny = points[i + 1]
        if (px == cx == nx) or (py == cy == ny):
            continue
        simplified.append((cx, cy))
    simplified.append(points[-1])
    return simplified


def _normalize(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return _remove_collinear(_dedupe_points(points))


def _to_bendpoints(points: list[tuple[int, int]]) -> list[BendPoint]:
    """Strip first/last (source/target anchors) and return middle points."""
    if len(points) <= 2:
        return []
    return [BendPoint(x=x, y=y) for x, y in points[1:-1]]


# ---------------------------------------------------------------------------
# Obstacle / collision detection
# ---------------------------------------------------------------------------

def _segment_hits_rect(
    x1: int, y1: int, x2: int, y2: int,
    node: Node,
    padding: int,
) -> bool:
    """Axis-aligned segment vs padded rectangle. Only H/V segments."""
    l = node.x - padding
    r = node.x + node.w + padding
    t = node.y - padding
    b = node.y + node.h + padding

    if x1 == x2:                             # vertical segment
        if not (l <= x1 <= r):
            return False
        return not (max(y1, y2) < t or min(y1, y2) > b)

    if y1 == y2:                             # horizontal segment
        if not (t <= y1 <= b):
            return False
        return not (max(x1, x2) < l or min(x1, x2) > r)

    return False


def _path_hits_obstacle(
    points: list[tuple[int, int]],
    obstacles: list[Node],
    skip_ids: frozenset[str],
    padding: int,
) -> bool:
    norm = _normalize(points)
    for i in range(len(norm) - 1):
        x1, y1 = norm[i]
        x2, y2 = norm[i + 1]
        for node in obstacles:
            if node.id in skip_ids:
                continue
            if _segment_hits_rect(x1, y1, x2, y2, node, padding):
                return True
    return False


def _path_is_clear(
    points: list[tuple[int, int]],
    obstacles: list[Node],
    source_id: str,
    target_id: str,
    padding: int,
) -> bool:
    return not _path_hits_obstacle(
        points, obstacles,
        frozenset({source_id, target_id}),
        padding,
    )


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _is_cross_layer(source: Node, target: Node) -> bool:
    """True when vertical distance dominates — arrow spans multiple layers."""
    return abs(_cy(target) - _cy(source)) > abs(_cx(target) - _cx(source))


def _try_minimal_route(
    source: Node,
    target: Node,
    obstacles: list[Node],
    cfg: LayoutConfig,
) -> list[tuple[int, int]] | None:
    """Try straight or single-bend routes first."""
    sy, ty = _cy(source), _cy(target)
    if _cx(target) >= _cx(source):
        start = (_right(source) + cfg.anchor_offset, sy)
        end   = (_left(target)  - cfg.anchor_offset, ty)
    else:
        start = (_left(source)  - cfg.anchor_offset, sy)
        end   = (_right(target) + cfg.anchor_offset, ty)

    candidates = [
        [start, end],
        [start, (end[0],   start[1]), end],
        [start, (start[0], end[1]),   end],
    ]
    for candidate in candidates:
        norm = _normalize(candidate)
        if _path_is_clear(norm, obstacles, source.id, target.id, cfg.route_padding):
            return norm
    return None


def _route_cross_layer(
    source: Node,
    target: Node,
    obstacles: list[Node],
    cfg: LayoutConfig,
    pair_index: int,
    side: str,
) -> list[BendPoint]:
    """Route a vertical-dominant (cross-layer) arrow via left/right lane."""
    lane_extra = cfg.lane_base + (pair_index // 2) * cfg.lane_step
    sy, ty = _cy(source), _cy(target)

    if ty >= sy:
        start = (_cx(source), _bottom(source) + cfg.anchor_offset)
        end   = (_cx(target), _top(target)    - cfg.anchor_offset)
    else:
        start = (_cx(source), _top(source)    - cfg.anchor_offset)
        end   = (_cx(target), _bottom(target) + cfg.anchor_offset)

    left_base  = min(_left(source),  _left(target))
    right_base = max(_right(source), _right(target))
    try_left_first = (side == "top")

    for i in range(12):
        extra = lane_extra + i * cfg.lane_step
        for try_left in ([True, False] if try_left_first else [False, True]):
            lane_x = (left_base - extra) if try_left else (right_base + extra)
            candidate = _normalize([start, (lane_x, start[1]), (lane_x, end[1]), end])
            if _path_is_clear(candidate, obstacles, source.id, target.id, cfg.route_padding):
                return _to_bendpoints(candidate)

    # Fallback: straight dogleg
    return _to_bendpoints(_normalize([start, (_cx(source), _cy(target)), end]))


def _route_same_layer(
    source: Node,
    target: Node,
    obstacles: list[Node],
    cfg: LayoutConfig,
    pair_index: int,
    pair_count: int,
    side: str,
) -> list[BendPoint]:
    """Route a horizontal-dominant (same-layer) arrow with staggered anchors."""
    lane_extra   = cfg.lane_base + (pair_index // 2) * cfg.lane_step
    anchor_off_y = int((pair_index - (pair_count - 1) / 2) * cfg.lane_step)
    sy, ty       = _cy(source), _cy(target)

    if _cx(target) >= _cx(source):
        start = (_right(source) + cfg.anchor_offset, sy + anchor_off_y)
        end   = (_left(target)  - cfg.anchor_offset, ty + anchor_off_y)
        x_dir = 1
    else:
        start = (_left(source)  - cfg.anchor_offset, sy + anchor_off_y)
        end   = (_right(target) + cfg.anchor_offset, ty + anchor_off_y)
        x_dir = -1

    # Prefer straight line if unobstructed
    if pair_count > 1:
        if _path_is_clear([start, end], obstacles, source.id, target.id, cfg.route_padding):
            return _to_bendpoints([start, end])

    top_lane    = min(_top(source),    _top(target))    - lane_extra + anchor_off_y
    bottom_lane = max(_bottom(source), _bottom(target)) + lane_extra + anchor_off_y
    out_x = start[0] + x_dir * lane_extra
    in_x  = end[0]   - x_dir * lane_extra

    if side == "top":
        ordered_lanes = [top_lane, bottom_lane]
    else:
        ordered_lanes = [bottom_lane, top_lane]

    candidates: list[list[tuple[int, int]]] = [
        [start, (out_x, start[1]), (out_x, lane), (in_x, lane), (in_x, end[1]), end]
        for lane in ordered_lanes
    ] + [
        _normalize([start, (end[0],   start[1]), end]),
        _normalize([start, (start[0], end[1]),   end]),
    ]

    for candidate in candidates:
        norm = _normalize(candidate)
        if _path_is_clear(norm, obstacles, source.id, target.id, cfg.route_padding):
            return _to_bendpoints(norm)

    return _to_bendpoints(_normalize(candidates[0]))


def _route_connection(
    source: Node,
    target: Node,
    obstacles: list[Node],
    cfg: LayoutConfig,
    pair_index: int = 0,
    pair_count: int = 1,
    direction: int = 1,
) -> list[BendPoint]:
    # Single relationship: try clean minimal route first
    if pair_count == 1:
        minimal = _try_minimal_route(source, target, obstacles, cfg)
        if minimal is not None:
            return _to_bendpoints(minimal)

    side = "top" if (pair_index + (0 if direction == 1 else 1)) % 2 == 0 else "bottom"

    if _is_cross_layer(source, target):
        return _route_cross_layer(source, target, obstacles, cfg, pair_index, side)
    else:
        return _route_same_layer(source, target, obstacles, cfg, pair_index, pair_count, side)


# ---------------------------------------------------------------------------
# Pair routing order
# ---------------------------------------------------------------------------

def _pair_key(a: str, b: str) -> tuple[str, str]:
    return (min(a, b), max(a, b))


def _build_pair_route_order(
    model: ArchimateModel,
    element_to_node: dict[str, str],
    nesting_rel_ids: set[str],
    rel_type_filter: set[str] | None,
) -> dict[str, tuple[int, int, int]]:
    """
    Returns rel_id -> (pair_index, pair_count, direction).
    direction: 1 = canonical, -1 = reverse.
    """
    grouped: dict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)

    for rel in model.relationships:
        if rel.id in nesting_rel_ids:
            continue
        if rel_type_filter is not None and rel.type not in rel_type_filter:
            continue
        src_nid = element_to_node.get(rel.source)
        tgt_nid = element_to_node.get(rel.target)
        if src_nid and tgt_nid:
            grouped[_pair_key(src_nid, tgt_nid)].append((rel.id, src_nid, tgt_nid))

    result: dict[str, tuple[int, int, int]] = {}
    for (canon_a, canon_b), items in grouped.items():
        items = sorted(items, key=lambda x: x[0])  # stable sort by rel_id
        for idx, (rel_id, src_nid, tgt_nid) in enumerate(items):
            direction = 1 if (src_nid, tgt_nid) == (canon_a, canon_b) else -1
            result[rel_id] = (idx, len(items), direction)

    return result


# ---------------------------------------------------------------------------
# Nesting index
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

    nested_ids: set[str] = {cid for kids in children_of.values() for cid in kids}
    return children_of, nesting_rel_ids, nested_ids


# ---------------------------------------------------------------------------
# Node building
# ---------------------------------------------------------------------------

def _node_size(
    element_id: str,
    children_of: dict[str, list[str]],
    cfg: LayoutConfig,
) -> tuple[int, int]:
    child_ids = children_of.get(element_id, [])
    if child_ids:
        w = max(cfg.node_w, len(child_ids) * (cfg.child_w + cfg.padding) + cfg.padding)
        h = cfg.node_h + cfg.child_h + cfg.padding * 3
    else:
        w, h = cfg.node_w, cfg.node_h
    return w, h


def _build_child_nodes(
    element_id: str,
    children_of: dict[str, list[str]],
    element_by_id: dict[str, Element],
    view_id: str,
    cfg: LayoutConfig,
) -> list[Node]:
    return [
        Node(
            id=f"{view_id}_node_{child_id}",
            element_id=child_id,
            x=cfg.padding + idx * (cfg.child_w + cfg.padding),
            y=cfg.padding + cfg.node_h,
            w=cfg.child_w,
            h=cfg.child_h,
            node_type="Element",
        )
        for idx, child_id in enumerate(children_of.get(element_id, []))
        if child_id in element_by_id
    ]


def _build_nodes_from_grid(
    elements: list[Element],
    element_by_id: dict[str, Element],
    children_of: dict[str, list[str]],
    layer_elements: dict[str, list[Element]],
    relationships: list,
    element_layer: dict[str, str],
    layer_order: list[str],
    view_id: str,
    cfg: LayoutConfig,
) -> tuple[list[Node], dict[str, str], dict[str, Node]]:
    """
    Place elements via smart grid and return:
      nodes, element_to_node, node_by_id
    """
    node_sizes = {el.id: _node_size(el.id, children_of, cfg) for el in elements}

    grid = build_smart_grid(
        layer_elements=layer_elements,
        layer_order=layer_order,
        relationships=relationships,
        element_layer=element_layer,
    )
    metrics = compute_grid_metrics(
        grid=grid,
        node_sizes=node_sizes,
        cfg=cfg,
    )

    nodes: list[Node] = []
    element_to_node: dict[str, str] = {}
    node_by_id: dict[str, Node] = {}

    for cell in grid.cells:
        element = element_by_id.get(cell.element_id)
        if not element:
            continue

        w, h   = node_sizes[cell.element_id]
        node_id = f"{view_id}_node_{cell.element_id}"
        children = _build_child_nodes(cell.element_id, children_of, element_by_id, view_id, cfg)

        node = Node(
            id=node_id,
            element_id=cell.element_id,
            x=metrics.x_of(cell.col),
            y=metrics.y_of(cell.row),
            w=w, h=h,
            node_type="Element",
            children=children,
        )
        nodes.append(node)
        node_by_id[node_id] = node
        element_to_node[cell.element_id] = node_id

        for child in children:
            if child.element_id:
                element_to_node[child.element_id] = child.id
            node_by_id[child.id] = child

    return nodes, element_to_node, node_by_id


def _build_connections_with_routing(
    model: ArchimateModel,
    element_to_node: dict[str, str],
    node_by_id: dict[str, Node],
    top_level_nodes: list[Node],
    nesting_rel_ids: set[str],
    view_id: str,
    cfg: LayoutConfig,
    rel_type_filter: set[str] | None = None,
) -> list[Connection]:
    pair_order = _build_pair_route_order(
        model, element_to_node, nesting_rel_ids, rel_type_filter
    )
    connections: list[Connection] = []

    for rel in model.relationships:
        if rel.id in nesting_rel_ids:
            continue
        if rel_type_filter is not None and rel.type not in rel_type_filter:
            continue

        src_nid = element_to_node.get(rel.source)
        tgt_nid = element_to_node.get(rel.target)
        if not src_nid or not tgt_nid:
            continue

        src_node = node_by_id.get(src_nid)
        tgt_node = node_by_id.get(tgt_nid)
        if not src_node or not tgt_node:
            continue

        pair_index, pair_count, direction = pair_order.get(rel.id, (0, 1, 1))
        bendpoints = _route_connection(
            src_node, tgt_node, top_level_nodes, cfg,
            pair_index=pair_index, pair_count=pair_count, direction=direction,
        )
        connections.append(Connection(
            id=f"{view_id}_conn_{rel.id}",
            relationship_id=rel.id,
            source_node_id=src_nid,
            target_node_id=tgt_nid,
            bendpoints=bendpoints,
        ))

    return connections


# ---------------------------------------------------------------------------
# Layer data preparation
# ---------------------------------------------------------------------------

def _prepare_layer_data(
    model: ArchimateModel,
    nested_element_ids: set[str],
    type_filter: set[str] | None = None,
) -> tuple[dict[str, list[Element]], dict[str, str]]:
    """
    Returns:
      layer_elements: layer_id -> [Element]  (filtered, no nested)
      element_layer:  element_id -> layer_id
    """
    layer_elements: dict[str, list[Element]] = defaultdict(list)
    element_layer: dict[str, str] = {}

    for element in model.elements:
        if element.id in nested_element_ids:
            continue
        if type_filter is not None and element.type not in type_filter:
            continue
        lid = TYPE_TO_LAYER.get(element.type, "other")
        layer_elements[lid].append(element)
        element_layer[element.id] = lid

    return layer_elements, element_layer


# ---------------------------------------------------------------------------
# Shared view builder
# ---------------------------------------------------------------------------

def _build_view(
    model: ArchimateModel,
    view_id: str,
    view_name: str,
    layer_order: list[str],
    type_filter: set[str] | None = None,
    rel_type_filter: set[str] | None = None,
    element_id_filter: set[str] | None = None,
    cfg: LayoutConfig = DEFAULT_CONFIG,
) -> View:
    """
    Generic view builder used by all four view generators.

    Parameters
    ----------
    layer_order       : which layers to include and in what order
    type_filter       : if set, only include elements of these types
    rel_type_filter   : if set, only draw connections of these rel types
    element_id_filter : if set, only include these specific element ids
    cfg               : layout constants
    """
    element_by_id = {e.id: e for e in model.elements}
    children_of, nesting_rel_ids, nested_ids = _build_nesting_index(model)

    combined_filter = type_filter
    layer_elements, element_layer = _prepare_layer_data(
        model, nested_ids, type_filter=combined_filter
    )

    # Optional further narrowing by element id
    if element_id_filter is not None:
        for lid in list(layer_elements.keys()):
            layer_elements[lid] = [
                e for e in layer_elements[lid] if e.id in element_id_filter
            ]

    elements = [
        e for e in model.elements
        if (type_filter is None or e.type in type_filter)
        and (element_id_filter is None or e.id in element_id_filter)
        and e.id not in nested_ids
    ]

    nodes, element_to_node, node_by_id = _build_nodes_from_grid(
        elements=elements,
        element_by_id=element_by_id,
        children_of=children_of,
        layer_elements=layer_elements,
        relationships=model.relationships,
        element_layer=element_layer,
        layer_order=layer_order,
        view_id=view_id,
        cfg=cfg,
    )

    connections = _build_connections_with_routing(
        model=model,
        element_to_node=element_to_node,
        node_by_id=node_by_id,
        top_level_nodes=nodes,
        nesting_rel_ids=nesting_rel_ids,
        view_id=view_id,
        cfg=cfg,
        rel_type_filter=rel_type_filter,
    )

    return View(id=view_id, name=view_name, nodes=nodes, connections=connections)


# ---------------------------------------------------------------------------
# Public view generators
# ---------------------------------------------------------------------------

def generate_application_view(
    model: ArchimateModel, view_id: str, view_name: str,
    cfg: LayoutConfig = DEFAULT_CONFIG,
) -> View:
    """Default layered view — all elements across all three layers."""
    return _build_view(
        model, view_id, view_name,
        layer_order=LAYER_IDS,
        cfg=cfg,
    )


def generate_application_cooperation_view(
    model: ArchimateModel, view_id: str, view_name: str,
    cfg: LayoutConfig = DEFAULT_CONFIG,
) -> View:
    """Application layer only — components, services, data objects."""
    return _build_view(
        model, view_id, view_name,
        layer_order=["application"],
        type_filter={"ApplicationComponent", "ApplicationService", "DataObject"},
        rel_type_filter={"Serving", "Realization", "Access", "Association", "Flow"},
        cfg=cfg,
    )


def generate_technology_view(
    model: ArchimateModel, view_id: str, view_name: str,
    cfg: LayoutConfig = DEFAULT_CONFIG,
) -> View:
    """Technology layer only — devices, nodes, system software."""
    return _build_view(
        model, view_id, view_name,
        layer_order=["technology"],
        type_filter={"Device", "Node", "SystemSoftware"},
        rel_type_filter={"Composition", "Aggregation", "Association"},
        cfg=cfg,
    )


def generate_integration_view(
    model: ArchimateModel, view_id: str, view_name: str,
    cfg: LayoutConfig = DEFAULT_CONFIG,
) -> View:
    """Cross-layer view — only elements that participate in integration relationships."""
    INTEGRATION_REL_TYPES = {"Assignment", "Realization", "Serving", "Triggering", "Flow"}

    element_map = {e.id: e for e in model.elements}
    integration_ids: set[str] = set()

    for rel in model.relationships:
        if rel.type not in INTEGRATION_REL_TYPES:
            continue
        src = element_map.get(rel.source)
        tgt = element_map.get(rel.target)
        if not src or not tgt:
            continue
        if TYPE_TO_LAYER.get(src.type) != TYPE_TO_LAYER.get(tgt.type):
            integration_ids.update({rel.source, rel.target})

    return _build_view(
        model, view_id, view_name,
        layer_order=LAYER_IDS,
        element_id_filter=integration_ids,
        rel_type_filter=INTEGRATION_REL_TYPES,
        cfg=cfg,
    )