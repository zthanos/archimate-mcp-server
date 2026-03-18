from __future__ import annotations

from archimate_mcp.config import LayoutConfig
from archimate_mcp.lanes import LaneAllocator
from archimate_mcp.layout import (
    _expand_horizontal_route_corridors,
    _path_hits_obstacle,
    _route_between_ports,
)
from archimate_mcp.models import Node
from archimate_mcp.ports import Edge, Point, Port


def _points_for_route(src_port: Port, tgt_port: Port, bendpoints) -> list[tuple[int, int]]:
    return [
        (src_port.point.x, src_port.point.y),
        *[(bp.x, bp.y) for bp in bendpoints],
        (tgt_port.point.x, tgt_port.point.y),
    ]


def test_route_between_ports_avoids_central_obstacle() -> None:
    cfg = LayoutConfig()
    lanes = LaneAllocator(
        h_step=cfg.lane_step,
        v_step=cfg.lane_step,
        padding=cfg.route_padding // 2,
    )
    blocker = Node(id="blocker", x=130, y=170, w=120, h=90)

    src_port = Port(
        node_id="src",
        edge=Edge.E,
        slot_idx=0,
        point=Point(80, 130),
    )
    tgt_port = Port(
        node_id="tgt",
        edge=Edge.N,
        slot_idx=0,
        point=Point(340, 320),
    )

    bendpoints = _route_between_ports(src_port, tgt_port, [blocker], cfg, lanes)
    points = _points_for_route(src_port, tgt_port, bendpoints)

    assert bendpoints
    assert not _path_hits_obstacle(points, [blocker], frozenset(), cfg.route_padding)


def test_route_between_ports_reserves_lanes_for_following_routes() -> None:
    cfg = LayoutConfig()
    lanes = LaneAllocator(
        h_step=cfg.lane_step,
        v_step=cfg.lane_step,
        padding=cfg.route_padding // 2,
    )
    blocker = Node(id="blocker", x=130, y=170, w=120, h=90)

    src_a = Port(node_id="src_a", edge=Edge.E, slot_idx=0, point=Point(80, 130))
    tgt_a = Port(node_id="tgt_a", edge=Edge.N, slot_idx=0, point=Point(340, 320))
    src_b = Port(node_id="src_b", edge=Edge.E, slot_idx=0, point=Point(80, 130))
    tgt_b = Port(node_id="tgt_b", edge=Edge.N, slot_idx=0, point=Point(340, 320))

    route_a = _route_between_ports(src_a, tgt_a, [blocker], cfg, lanes)
    route_b = _route_between_ports(src_b, tgt_b, [blocker], cfg, lanes)

    assert route_a
    assert route_b
    assert [(bp.x, bp.y) for bp in route_a] != [(bp.x, bp.y) for bp in route_b]


def test_route_between_ports_bypasses_same_row_intermediate_obstacles() -> None:
    cfg = LayoutConfig()
    lanes = LaneAllocator(
        h_step=cfg.lane_step,
        v_step=cfg.lane_step,
        padding=cfg.route_padding // 2,
    )
    blocker_a = Node(id="blocker_a", x=220, y=100, w=120, h=80)
    blocker_b = Node(id="blocker_b", x=380, y=100, w=120, h=80)

    src_port = Port(node_id="src", edge=Edge.E, slot_idx=0, point=Point(120, 140))
    tgt_port = Port(node_id="tgt", edge=Edge.W, slot_idx=0, point=Point(620, 140))

    bendpoints = _route_between_ports(src_port, tgt_port, [blocker_a, blocker_b], cfg, lanes)
    points = _points_for_route(src_port, tgt_port, bendpoints)

    assert bendpoints
    assert not _path_hits_obstacle(
        points,
        [blocker_a, blocker_b],
        frozenset(),
        cfg.route_padding,
    )


def test_route_between_ports_keeps_explicit_anchor_escape_points_when_clear() -> None:
    cfg = LayoutConfig()
    lanes = LaneAllocator(
        h_step=cfg.lane_step,
        v_step=cfg.lane_step,
        padding=cfg.route_padding // 2,
    )

    src_port = Port(node_id="src", edge=Edge.E, slot_idx=0, point=Point(120, 140))
    tgt_port = Port(node_id="tgt", edge=Edge.W, slot_idx=0, point=Point(420, 140))

    bendpoints = _route_between_ports(src_port, tgt_port, [], cfg, lanes)

    assert len(bendpoints) >= 2
    assert bendpoints[0].x > src_port.point.x
    assert bendpoints[-1].x < tgt_port.point.x


def test_expand_horizontal_route_corridors_pushes_lower_rows_down() -> None:
    cfg = LayoutConfig()
    src = Node(id="src", x=100, y=100, w=120, h=80)
    tgt = Node(id="tgt", x=620, y=100, w=120, h=80)
    blocker = Node(id="blocker", x=320, y=100, w=120, h=80)
    lower = Node(id="lower", x=100, y=240, w=120, h=80)

    nodes = [src, tgt, blocker, lower]
    node_by_id = {node.id: node for node in nodes}

    _expand_horizontal_route_corridors(
        top_level_nodes=nodes,
        visible=[("rel_1", "src", "tgt")],
        node_by_id=node_by_id,
        cfg=cfg,
    )

    assert lower.y > 240
