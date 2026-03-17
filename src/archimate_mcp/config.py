from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayoutConfig:
    """
    All layout and routing constants in one place.

    Passed explicitly through the pipeline:
      layout.py -> grid.py (via compute_grid_metrics)

    Override per-view for different visual styles.
    """
    # Node dimensions
    node_w:        int = 220
    node_h:        int = 70
    child_w:       int = 170
    child_h:       int = 55

    # Spacing
    h_gap:         int = 120   # horizontal gap between nodes in same layer
    layer_v_gap:   int = 240   # vertical gap between layers
    padding:       int = 24    # padding inside container nodes
    margin_left:   int = 100   # canvas left margin
    margin_top:    int = 80    # canvas top margin

    # Routing
    anchor_offset: int = 16    # connection exit/entry offset from node edge
    route_padding: int = 36    # clearance around obstacles during routing
    lane_base:     int = 60    # base offset for routed lanes
    lane_step:     int = 36    # increment per additional lane


DEFAULT_CONFIG = LayoutConfig()