from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import NamedTuple

from .models import Node


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------

class Edge(str, Enum):
    N = "N"   # top
    S = "S"   # bottom
    W = "W"   # left
    E = "E"   # right

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
    node_id:  str
    edge:     Edge
    slot_idx: int    # 0 = first slot, 1 = second, ...
    point:    Point  # absolute pixel coordinates


# ---------------------------------------------------------------------------
# Port assignment
# ---------------------------------------------------------------------------

@dataclass
class _EdgeSlots:
    """Tracks slot reservations for one edge of one node."""
    node:  Node
    edge:  Edge
    slots: list[str] = field(default_factory=list)  # rel_ids in order

    def reserve(self, rel_id: str) -> int:
        """Add rel_id to this edge and return its slot index."""
        if rel_id not in self.slots:
            self.slots.append(rel_id)
        return self.slots.index(rel_id)

    def point_for(self, slot_idx: int) -> Point:
        """
        Compute the pixel coordinate for a slot.

        Slots are evenly distributed along the edge, centred on the midpoint.
        For N/S edges: distribute along X.
        For W/E edges: distribute along Y.
        """
        n = len(self.slots)
        step = (
            self.node.w / (n + 1) if self.edge.is_horizontal is False
            else self.node.h / (n + 1)
        )

        if self.edge in (Edge.N, Edge.S):
            x = int(self.node.x + step * (slot_idx + 1))
            y = self.node.y if self.edge == Edge.N else self.node.y + self.node.h
        else:  # W, E
            x = self.node.x if self.edge == Edge.W else self.node.x + self.node.w
            y = int(self.node.y + step * (slot_idx + 1))

        return Point(x, y)


def _preferred_edge(src: Node, tgt: Node) -> tuple[Edge, Edge]:
    """
    Determine which edges a connection should use based on
    the relative positions of the two nodes.

    Rules (in priority order):
      1. If vertical distance dominates → S/N (cross-layer)
      2. If target is to the right → E/W
      3. If target is to the left  → W/E
    """
    src_cx = src.x + src.w // 2
    src_cy = src.y + src.h // 2
    tgt_cx = tgt.x + tgt.w // 2
    tgt_cy = tgt.y + tgt.h // 2

    dx = abs(tgt_cx - src_cx)
    dy = abs(tgt_cy - src_cy)

    if dy > dx:
        # Cross-layer: vertical dominant
        src_edge = Edge.S if tgt_cy > src_cy else Edge.N
        tgt_edge = src_edge.opposite
    elif tgt_cx >= src_cx:
        src_edge, tgt_edge = Edge.E, Edge.W
    else:
        src_edge, tgt_edge = Edge.W, Edge.E

    return src_edge, tgt_edge


@dataclass
class NodePortMap:
    """
    All port slots for all nodes in a view.
    Populated by assign_ports(); queried by the router.
    """
    # node_id -> edge -> _EdgeSlots
    _slots: dict[str, dict[Edge, _EdgeSlots]] = field(default_factory=dict)

    def _get_edge_slots(self, node: Node, edge: Edge) -> _EdgeSlots:
        if node.id not in self._slots:
            self._slots[node.id] = {}
        if edge not in self._slots[node.id]:
            self._slots[node.id][edge] = _EdgeSlots(node=node, edge=edge)
        return self._slots[node.id][edge]

    def reserve(self, node: Node, edge: Edge, rel_id: str) -> Port:
        """Reserve a slot on node's edge for rel_id. Returns the Port."""
        es = self._get_edge_slots(node, edge)
        slot_idx = es.reserve(rel_id)
        # Point is computed after all reservations (so n is final).
        # We store a placeholder and resolve lazily in port_for().
        return Port(
            node_id=node.id,
            edge=edge,
            slot_idx=slot_idx,
            point=Point(0, 0),  # resolved lazily
        )

    def port_for(self, node: Node, edge: Edge, rel_id: str) -> Port:
        """Return the fully resolved Port (with correct pixel point) for rel_id."""
        es = self._get_edge_slots(node, edge)
        slot_idx = es.slots.index(rel_id)
        return Port(
            node_id=node.id,
            edge=edge,
            slot_idx=slot_idx,
            point=es.point_for(slot_idx),
        )


def assign_ports(
    node_by_id: dict[str, Node],
    connections: list[tuple[str, str, str]],  # [(rel_id, src_node_id, tgt_node_id)]
) -> dict[str, tuple[Port, Port]]:
    """
    Assign ports for every connection.

    Pass 1: reserve slots (determines edge and n — needed for spacing).
    Pass 2: resolve pixel coordinates (now n is final for each edge).

    Returns: rel_id -> (src_port, tgt_port)
    """
    npm = NodePortMap()

    # Pass 1 — reserve (order matters for stable slot assignment)
    edge_map: dict[str, tuple[Edge, Edge]] = {}
    for rel_id, src_nid, tgt_nid in sorted(connections, key=lambda x: x[0]):
        src = node_by_id.get(src_nid)
        tgt = node_by_id.get(tgt_nid)
        if not src or not tgt:
            continue
        src_edge, tgt_edge = _preferred_edge(src, tgt)
        edge_map[rel_id] = (src_edge, tgt_edge)
        npm.reserve(src, src_edge, rel_id)
        npm.reserve(tgt, tgt_edge, rel_id)

    # Pass 2 — resolve pixel coordinates
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