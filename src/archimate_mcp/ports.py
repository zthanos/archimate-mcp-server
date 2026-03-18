from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import NamedTuple

from .models import Node


class Edge(str, Enum):
    N = "N"
    S = "S"
    W = "W"
    E = "E"

    @property
    def opposite(self) -> "Edge":
        return {Edge.N: Edge.S, Edge.S: Edge.N, Edge.W: Edge.E, Edge.E: Edge.W}[self]

    @property
    def is_horizontal(self) -> bool:
        return self in (Edge.W, Edge.E)

    @property
    def is_vertical(self) -> bool:
        return self in (Edge.N, Edge.S)


class Point(NamedTuple):
    x: int
    y: int


@dataclass(frozen=True)
class Port:
    node_id: str
    edge: Edge
    slot_idx: int
    point: Point


@dataclass(frozen=True)
class _EdgeReservation:
    rel_id: str
    other_node: Node


@dataclass
class _EdgeSlots:
    """Tracks slot reservations for one edge of one node."""

    node: Node
    edge: Edge
    slots: list[str] = field(default_factory=list)

    def reserve(self, rel_id: str) -> int:
        if rel_id not in self.slots:
            self.slots.append(rel_id)
        return self.slots.index(rel_id)

    def set_slot_order(self, ordered_rel_ids: list[str]) -> None:
        self.slots = list(ordered_rel_ids)

    def point_for(self, slot_idx: int) -> Point:
        """
        Compute the pixel coordinate for a slot.

        Slots are evenly distributed along the edge.
        For N/S edges they are distributed along X.
        For W/E edges they are distributed along Y.
        """
        n = len(self.slots)
        step = self.node.w / (n + 1) if not self.edge.is_horizontal else self.node.h / (n + 1)

        if self.edge in (Edge.N, Edge.S):
            x = int(self.node.x + step * (slot_idx + 1))
            y = self.node.y if self.edge == Edge.N else self.node.y + self.node.h
        else:
            x = self.node.x if self.edge == Edge.W else self.node.x + self.node.w
            y = int(self.node.y + step * (slot_idx + 1))

        return Point(x, y)


def _preferred_edge(src: Node, tgt: Node) -> tuple[Edge, Edge]:
    """Pick the source and target edges to connect based on relative geometry."""
    src_cx = src.x + src.w // 2
    src_cy = src.y + src.h // 2
    tgt_cx = tgt.x + tgt.w // 2
    tgt_cy = tgt.y + tgt.h // 2

    src_top, src_bottom = src.y, src.y + src.h
    tgt_top, tgt_bottom = tgt.y, tgt.y + tgt.h
    vertical_overlap = src_top <= tgt_bottom and tgt_top <= src_bottom

    if not vertical_overlap:
        src_edge = Edge.S if tgt_cy > src_cy else Edge.N
        tgt_edge = src_edge.opposite
    elif tgt_cx >= src_cx:
        src_edge, tgt_edge = Edge.E, Edge.W
    else:
        src_edge, tgt_edge = Edge.W, Edge.E

    return src_edge, tgt_edge


def _slot_sort_key(node: Node, edge: Edge, other: Node) -> tuple[int, int, int]:
    """
    Sort reservations along an edge so port order follows the opposite endpoints.

    This reduces local crossings before routing.
    """
    other_cx = other.x + other.w // 2
    other_cy = other.y + other.h // 2
    node_cx = node.x + node.w // 2
    node_cy = node.y + node.h // 2

    if edge in (Edge.N, Edge.S):
        return (other_cx, other_cy, abs(other_cx - node_cx))
    return (other_cy, other_cx, abs(other_cy - node_cy))


@dataclass
class NodePortMap:
    """
    All port slots for all nodes in a view.
    Populated by assign_ports(); queried by the router.
    """

    _slots: dict[str, dict[Edge, _EdgeSlots]] = field(default_factory=dict)

    def _get_edge_slots(self, node: Node, edge: Edge) -> _EdgeSlots:
        if node.id not in self._slots:
            self._slots[node.id] = {}
        if edge not in self._slots[node.id]:
            self._slots[node.id][edge] = _EdgeSlots(node=node, edge=edge)
        return self._slots[node.id][edge]

    def reserve(self, node: Node, edge: Edge, rel_id: str) -> Port:
        es = self._get_edge_slots(node, edge)
        slot_idx = es.reserve(rel_id)
        return Port(node_id=node.id, edge=edge, slot_idx=slot_idx, point=Point(0, 0))

    def order_edge(self, node: Node, edge: Edge, ordered_rel_ids: list[str]) -> None:
        self._get_edge_slots(node, edge).set_slot_order(ordered_rel_ids)

    def port_for(self, node: Node, edge: Edge, rel_id: str) -> Port:
        es = self._get_edge_slots(node, edge)
        slot_idx = es.slots.index(rel_id)
        return Port(node_id=node.id, edge=edge, slot_idx=slot_idx, point=es.point_for(slot_idx))


def _apply_edge_ordering(
    node_port_map: NodePortMap,
    reservations: dict[tuple[str, Edge], list[_EdgeReservation]],
    node_by_id: dict[str, Node],
) -> None:
    """Apply geometric ordering to all reserved edge slots."""
    for (node_id, edge), entries in reservations.items():
        node = node_by_id.get(node_id)
        if node is None:
            continue
        ordered_rel_ids = [
            entry.rel_id
            for entry in sorted(entries, key=lambda entry: _slot_sort_key(node, edge, entry.other_node))
        ]
        node_port_map.order_edge(node, edge, ordered_rel_ids)


def assign_ports(
    node_by_id: dict[str, Node],
    connections: list[tuple[str, str, str]],
) -> dict[str, tuple[Port, Port]]:
    """
    Assign ports for every connection.

    Pass 1: reserve edge usage and collect geometric ordering hints.
    Pass 2: order the slots on each edge to reduce local crossings.
    Pass 3: resolve absolute port coordinates.
    """
    npm = NodePortMap()
    edge_map: dict[str, tuple[Edge, Edge]] = {}
    reservations: dict[tuple[str, Edge], list[_EdgeReservation]] = defaultdict(list)

    for rel_id, src_nid, tgt_nid in sorted(connections, key=lambda item: item[0]):
        src = node_by_id.get(src_nid)
        tgt = node_by_id.get(tgt_nid)
        if not src or not tgt:
            continue

        src_edge, tgt_edge = _preferred_edge(src, tgt)
        edge_map[rel_id] = (src_edge, tgt_edge)
        npm.reserve(src, src_edge, rel_id)
        npm.reserve(tgt, tgt_edge, rel_id)
        reservations[(src.id, src_edge)].append(_EdgeReservation(rel_id=rel_id, other_node=tgt))
        reservations[(tgt.id, tgt_edge)].append(_EdgeReservation(rel_id=rel_id, other_node=src))

    _apply_edge_ordering(npm, reservations, node_by_id)

    result: dict[str, tuple[Port, Port]] = {}
    for rel_id, src_nid, tgt_nid in connections:
        src = node_by_id.get(src_nid)
        tgt = node_by_id.get(tgt_nid)
        if not src or not tgt:
            continue
        src_edge, tgt_edge = edge_map[rel_id]
        result[rel_id] = (
            npm.port_for(src, src_edge, rel_id),
            npm.port_for(tgt, tgt_edge, rel_id),
        )

    return result
