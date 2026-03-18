from __future__ import annotations

from archimate_mcp.models import Node
from archimate_mcp.ports import Edge, assign_ports


def test_assign_ports_orders_east_edge_by_target_vertical_position() -> None:
    source = Node(id="src", x=100, y=100, w=120, h=80)
    target_top = Node(id="t1", x=320, y=80, w=120, h=80)
    target_mid = Node(id="t2", x=320, y=140, w=120, h=80)
    target_bottom = Node(id="t3", x=320, y=170, w=120, h=80)

    node_by_id = {
        source.id: source,
        target_top.id: target_top,
        target_mid.id: target_mid,
        target_bottom.id: target_bottom,
    }
    connections = [
        ("rel_mid", "src", "t2"),
        ("rel_bottom", "src", "t3"),
        ("rel_top", "src", "t1"),
    ]

    port_map = assign_ports(node_by_id, connections)

    src_ports = {
        rel_id: src_port
        for rel_id, (src_port, _) in port_map.items()
    }

    assert src_ports["rel_top"].edge == Edge.E
    assert src_ports["rel_mid"].edge == Edge.E
    assert src_ports["rel_bottom"].edge == Edge.E
    assert src_ports["rel_top"].slot_idx < src_ports["rel_mid"].slot_idx < src_ports["rel_bottom"].slot_idx
