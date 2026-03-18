from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from .config import DEFAULT_CONFIG, LayoutConfig
from .grid import build_smart_grid, compute_grid_metrics
from .lanes import LaneAllocator
from .models import ArchimateModel, BendPoint, Connection, Element, Node, View
from .ports import Edge, Port, assign_ports

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

    # Diagonal segment — use separating axis test (AABB vs line segment)
    # Fast reject: bounding boxes don't overlap
    seg_l, seg_r = min(x1, x2), max(x1, x2)
    seg_t, seg_b = min(y1, y2), max(y1, y2)
    if seg_r < l or seg_l > r or seg_b < t or seg_t > b:
        return False

    # Check if any corner of the rect is on opposite sides of the line
    # Line equation: (y2-y1)*x - (x2-x1)*y + (x2-x1)*y1 - (y2-y1)*x1 = 0
    dx, dy = x2 - x1, y2 - y1
    def _sign(px: int, py: int) -> float:
        return dy * px - dx * py + dx * y1 - dy * x1

    corners = [_sign(l, t), _sign(r, t), _sign(l, b), _sign(r, b)]
    if all(c > 0 for c in corners) or all(c < 0 for c in corners):
        return False   # rect entirely on one side of the line → no intersection

    return True


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


def _horizontal_blockers(
    x1: int,
    x2: int,
    y: int,
    obstacles: list[Node],
    skip_ids: frozenset[str],
    padding: int,
) -> list[Node]:
    """Return obstacles intersected by a horizontal segment."""
    blockers: list[Node] = []
    for node in obstacles:
        if node.id in skip_ids:
            continue
        if _segment_hits_rect(x1, y, x2, y, node, padding):
            blockers.append(node)
    return blockers


def _expand_horizontal_route_corridors(
    top_level_nodes: list[Node],
    visible: list[tuple[str, str, str]],
    node_by_id: dict[str, Node],
    cfg: LayoutConfig,
) -> None:
    """
    Create extra vertical space below crowded same-row relations.

    If a long horizontal relation is blocked by intermediate elements, we open a
    transit corridor by shifting all lower rows down. This gives the router a
    real empty band instead of forcing a tight bypass.
    """
    cuts: list[int] = []

    for _, src_nid, tgt_nid in visible:
        src = node_by_id.get(src_nid)
        tgt = node_by_id.get(tgt_nid)
        if src is None or tgt is None:
            continue

        src_cy = _cy(src)
        tgt_cy = _cy(tgt)
        if abs(src_cy - tgt_cy) > max(src.h, tgt.h) // 2:
            continue

        y = (src_cy + tgt_cy) // 2
        blockers = _horizontal_blockers(
            _cx(src),
            _cx(tgt),
            y,
            top_level_nodes,
            frozenset({src.id, tgt.id}),
            cfg.route_padding,
        )
        if blockers:
            cuts.append(max(_bottom(src), _bottom(tgt)))

    if not cuts:
        return

    extra_gap = cfg.node_h + cfg.row_v_gap
    accumulated_shift = 0
    for cut in sorted(set(cuts)):
        threshold = cut + accumulated_shift
        for node in top_level_nodes:
            if node.y >= threshold:
                node.y += extra_gap
        accumulated_shift += extra_gap


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _band_h(y1: int, y2: int, cfg: LayoutConfig) -> tuple[int, int]:
    lo, hi = min(y1, y2), max(y1, y2)
    margin = cfg.lane_base
    return (lo + margin, hi - margin)


def _band_v(x1: int, x2: int, cfg: LayoutConfig) -> tuple[int, int]:
    lo, hi = min(x1, x2), max(x1, x2)
    margin = cfg.lane_base
    return (lo + margin, hi - margin)


def _route_between_ports(
    src_port: Port,
    tgt_port: Port,
    obstacles: list[Node],
    cfg: LayoutConfig,
    lanes: LaneAllocator,
) -> list[BendPoint]:
    """
    Route between two pre-assigned port points using lane allocation.

    Path: src_port.point → escape → lane travel → entry → tgt_port.point
    """
    sx, sy = src_port.point.x, src_port.point.y
    tx, ty = tgt_port.point.x, tgt_port.point.y
    rel_id = f"{src_port.node_id}->{tgt_port.node_id}"
    skip   = frozenset({src_port.node_id, tgt_port.node_id})
    gap    = cfg.anchor_offset

    def escape(port: Port) -> tuple[int, int]:
        x, y = port.point.x, port.point.y
        if port.edge == Edge.E: return (x + gap, y)
        if port.edge == Edge.W: return (x - gap, y)
        if port.edge == Edge.S: return (x, y + gap)
        return (x, y - gap)

    p0 = escape(src_port)
    p3 = escape(tgt_port)
    src_vertical = src_port.edge in (Edge.N, Edge.S)

    def commit_h_lane(y: int, x1: int, x2: int, band: tuple[int, int]) -> None:
        if x1 != x2:
            lanes.reserve_h_lane(band, y, min(x1, x2), max(x1, x2), rel_id)

    def commit_v_lane(x: int, y1: int, y2: int, band: tuple[int, int]) -> None:
        if y1 != y2:
            lanes.reserve_v_lane(band, x, min(y1, y2), max(y1, y2), rel_id)

    def try_path(
        points: list[tuple[int, int]],
        h_reservations: list[tuple[tuple[int, int], int, int, int]],
        v_reservations: list[tuple[tuple[int, int], int, int, int]],
    ) -> list[BendPoint] | None:
        candidate = _normalize(points)
        if len(candidate) <= 2 and len(points) >= 4:
            # Keep explicit escape/entry anchors even when the route is perfectly straight.
            candidate = _dedupe_points(points)
        if not _path_is_clear(
            candidate,
            obstacles,
            src_port.node_id,
            tgt_port.node_id,
            cfg.route_padding,
        ):
            return None

        for band, y, x1, x2 in h_reservations:
            if x1 == x2:
                continue
            if not lanes.can_use_h_lane(band, y, min(x1, x2), max(x1, x2), obstacles, skip):
                return None

        for band, x, y1, y2 in v_reservations:
            if y1 == y2:
                continue
            if not lanes.can_use_v_lane(band, x, min(y1, y2), max(y1, y2), obstacles, skip):
                return None

        for band, y, x1, x2 in h_reservations:
            commit_h_lane(y, x1, x2, band)
        for band, x, y1, y2 in v_reservations:
            commit_v_lane(x, y1, y2, band)
        return _to_bendpoints(candidate)

    if not src_vertical and p0[1] == p3[1]:
        blockers = _horizontal_blockers(
            p0[0],
            p3[0],
            p0[1],
            obstacles,
            skip,
            cfg.route_padding,
        )
        if blockers:
            top_bound = min(node.y - cfg.route_padding for node in blockers)
            bottom_bound = max(node.y + node.h + cfg.route_padding for node in blockers)
            for step_idx in range(8):
                offset = cfg.lane_base + step_idx * cfg.lane_step
                for lane_y in (top_bound - offset, bottom_bound + offset):
                    h_band = (lane_y - cfg.lane_step, lane_y + cfg.lane_step)
                    routed = try_path(
                        [(sx, sy), p0, (p0[0], lane_y), (p3[0], lane_y), p3, (tx, ty)],
                        [(h_band, lane_y, p0[0], p3[0])],
                        [],
                    )
                    if routed is not None:
                        return routed

    if src_vertical:
        band = _band_h(p0[1], p3[1], cfg)
        if band[0] < band[1]:
            for lane_y in lanes.iter_h_lanes(band):
                routed = try_path(
                    [(sx, sy), p0, (p0[0], lane_y), (p3[0], lane_y), p3, (tx, ty)],
                    [(band, lane_y, p0[0], p3[0])],
                    [],
                )
                if routed is not None:
                    return routed
    else:
        band = _band_v(p0[0], p3[0], cfg)
        if band[0] < band[1]:
            for lane_x in lanes.iter_v_lanes(band):
                routed = try_path(
                    [(sx, sy), p0, (lane_x, p0[1]), (lane_x, p3[1]), p3, (tx, ty)],
                    [],
                    [(band, lane_x, p0[1], p3[1])],
                )
                if routed is not None:
                    return routed

    h_band = _band_h(p0[1], p3[1], cfg)
    v_band = _band_v(p0[0], p3[0], cfg)
    if h_band[0] < h_band[1] and v_band[0] < v_band[1]:
        h_candidates = lanes.iter_h_lanes(h_band)[:8]
        v_candidates = lanes.iter_v_lanes(v_band)[:8]
        for lane_y in h_candidates:
            for lane_x in v_candidates:
                routed = try_path(
                    [(sx, sy), p0, (p0[0], lane_y), (lane_x, lane_y), (lane_x, p3[1]), p3, (tx, ty)],
                    [(h_band, lane_y, p0[0], lane_x)],
                    [(v_band, lane_x, lane_y, p3[1])],
                )
                if routed is not None:
                    return routed

                routed = try_path(
                    [(sx, sy), p0, (lane_x, p0[1]), (lane_x, lane_y), (p3[0], lane_y), p3, (tx, ty)],
                    [(h_band, lane_y, lane_x, p3[0])],
                    [(v_band, lane_x, p0[1], lane_y)],
                )
                if routed is not None:
                    return routed

    for corner in [(p0[0], p3[1]), (p3[0], p0[1])]:
        candidate = _normalize([(sx, sy), p0, corner, p3, (tx, ty)])
        if _path_is_clear(candidate, obstacles, src_port.node_id, tgt_port.node_id, cfg.route_padding):
            return _to_bendpoints(candidate)

    escaped_straight = _normalize([(sx, sy), p0, p3, (tx, ty)])
    if _path_is_clear(
        escaped_straight,
        obstacles,
        src_port.node_id,
        tgt_port.node_id,
        cfg.route_padding,
    ):
        return _to_bendpoints(escaped_straight)

    for i in range(12):
        for dy in [-(cfg.lane_base + i * cfg.lane_step), (cfg.lane_base + i * cfg.lane_step)]:
            candidate = _normalize([(sx, sy), (p0[0], p0[1] + dy), (p3[0], p0[1] + dy), (tx, ty)])
            if _path_is_clear(candidate, obstacles, src_port.node_id, tgt_port.node_id, cfg.route_padding):
                return _to_bendpoints(candidate)
        for dx in [-(cfg.lane_base + i * cfg.lane_step), (cfg.lane_base + i * cfg.lane_step)]:
            candidate = _normalize([(sx, sy), (p0[0] + dx, p0[1]), (p0[0] + dx, p3[1]), (tx, ty)])
            if _path_is_clear(candidate, obstacles, src_port.node_id, tgt_port.node_id, cfg.route_padding):
                return _to_bendpoints(candidate)

    return _to_bendpoints(_normalize([(sx, sy), p0, (p0[0], p3[1]), p3, (tx, ty)]))


# ---------------------------------------------------------------------------
# Nesting index
# ---------------------------------------------------------------------------

def _build_nesting_index(
    model: ArchimateModel,
) -> tuple[dict[str, list[str]], set[str], set[str]]:
    element_by_id = {e.id: e for e in model.elements}
    children_of: dict[str, list[str]] = defaultdict(list)
    nesting_rel_ids: set[str] = set()

    # Collect candidate children (same-type Composition/Aggregation)
    candidate_children: dict[str, list[str]] = defaultdict(list)  # parent -> [child]
    candidate_rel_ids: dict[str, str] = {}  # child_id -> rel_id

    for rel in model.relationships:
        if rel.type not in NESTING_TYPES:
            continue
        src = element_by_id.get(rel.source)
        tgt = element_by_id.get(rel.target)
        if src and tgt and src.type == tgt.type:
            candidate_children[rel.source].append(rel.target)
            candidate_rel_ids[tgt.id] = rel.id

    # Only nest a child if it has NO outgoing relationships to other elements
    # (i.e. it is truly a "contained" element with no independent connections)
    # This prevents elements like dev_app1 (which hosts nd_k8s) from being
    # hidden inside a container while still having cross-element relationships.
    outgoing_targets: dict[str, set[str]] = defaultdict(set)
    for rel in model.relationships:
        outgoing_targets[rel.source].add(rel.target)

    for parent_id, child_ids in candidate_children.items():
        for child_id in child_ids:
            child_targets = outgoing_targets.get(child_id, set())
            # Nest only if the child has no outgoing relationships
            # (other than back to its parent)
            external_targets = child_targets - {parent_id}
            if not external_targets:
                children_of[parent_id].append(child_id)
                nesting_rel_ids.add(candidate_rel_ids[child_id])

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

    grid, layer_boundary_rows = build_smart_grid(
        layer_elements=layer_elements,
        layer_order=layer_order,
        relationships=relationships,
        element_layer=element_layer,
        max_cols_per_row=cfg.max_cols_per_row,
    )
    metrics = compute_grid_metrics(
        grid=grid,
        node_sizes=node_sizes,
        cfg=cfg,
        layer_boundary_rows=layer_boundary_rows,
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
    # Collect visible connections
    visible: list[tuple[str, str, str]] = []
    for rel in model.relationships:
        if rel.id in nesting_rel_ids:
            continue
        if rel_type_filter is not None and rel.type not in rel_type_filter:
            continue
        src_nid = element_to_node.get(rel.source)
        tgt_nid = element_to_node.get(rel.target)
        if src_nid and tgt_nid:
            visible.append((rel.id, src_nid, tgt_nid))

    # Assign ports — determines exit/entry points for every connection
    _expand_horizontal_route_corridors(top_level_nodes, visible, node_by_id, cfg)
    port_map = assign_ports(node_by_id, visible)

    # One LaneAllocator per view — shared across all connections
    lanes = LaneAllocator(
        h_step=cfg.lane_step,
        v_step=cfg.lane_step,
        padding=cfg.route_padding // 2,
    )

    connections: list[Connection] = []
    for rel_id, src_nid, tgt_nid in visible:
        ports = port_map.get(rel_id)
        if not ports:
            continue
        src_port, tgt_port = ports

        bendpoints = _route_between_ports(
            src_port, tgt_port, top_level_nodes, cfg, lanes
        )
        connections.append(Connection(
            id=f"{view_id}_conn_{rel_id}",
            relationship_id=rel_id,
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
