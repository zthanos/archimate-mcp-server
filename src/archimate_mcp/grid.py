from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from .config import LayoutConfig


@dataclass
class GridCell:
    row: int
    col: int
    element_id: str


@dataclass
class PlacementGrid:
    """
    Sparse grid where:
      row = vertical position in the placement lattice
      col = horizontal position in the placement lattice
    """

    cells: list[GridCell] = field(default_factory=list)
    _occupied: dict[tuple[int, int], str] = field(default_factory=dict, repr=False)
    _element_pos: dict[str, tuple[int, int]] = field(default_factory=dict, repr=False)

    def place(self, row: int, col: int, element_id: str) -> int:
        """Place an element at (row, col), shifting right until a free slot exists."""
        while (row, col) in self._occupied:
            col += 1
        self._occupied[(row, col)] = element_id
        self._element_pos[element_id] = (row, col)
        self.cells.append(GridCell(row=row, col=col, element_id=element_id))
        return col

    def col_of(self, element_id: str) -> int | None:
        pos = self._element_pos.get(element_id)
        return pos[1] if pos else None

    def row_of(self, element_id: str) -> int | None:
        pos = self._element_pos.get(element_id)
        return pos[0] if pos else None

    def elements_in_row(self, row: int) -> list[GridCell]:
        return sorted((c for c in self.cells if c.row == row), key=lambda c: c.col)

    def is_occupied(self, row: int, col: int) -> bool:
        return (row, col) in self._occupied

    @property
    def max_col(self) -> int:
        return max((c.col for c in self.cells), default=0)

    @property
    def max_row(self) -> int:
        return max((c.row for c in self.cells), default=0)


@dataclass(frozen=True)
class ComponentPlacement:
    positions: dict[str, tuple[int, int]]

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        rows = [row for row, _ in self.positions.values()]
        cols = [col for _, col in self.positions.values()]
        return min(rows), max(rows), min(cols), max(cols)


@dataclass
class _LayerPlacementContext:
    element_ids: list[str]
    same_layer_neighbors: dict[str, list[str]]
    positions: dict[str, tuple[int, int]] = field(default_factory=dict)
    occupied: dict[tuple[int, int], str] = field(default_factory=dict)
    queue: deque[str] = field(default_factory=deque)
    visited: set[str] = field(default_factory=set)

    def place(self, element_id: str, row: int, col: int) -> None:
        current = self.positions.get(element_id)
        if current is not None:
            self.occupied.pop(current, None)
        self.positions[element_id] = (row, col)
        self.occupied[(row, col)] = element_id

    def is_free(self, row: int, col: int, moving_element: str | None = None) -> bool:
        occupant = self.occupied.get((row, col))
        return occupant is None or occupant == moving_element

    def neighbors_of(self, element_id: str) -> list[str]:
        return self.same_layer_neighbors.get(element_id, [])


_DIRECTION_ORDER: tuple[str, ...] = ("E", "S", "W", "N")
_DIRECTION_DELTAS: dict[str, tuple[int, int]] = {
    "E": (0, 1),
    "S": (1, 0),
    "W": (0, -1),
    "N": (-1, 0),
}


def _build_same_layer_neighbor_map(
    relationships: list,
    element_layer: dict[str, str],
) -> dict[str, list[str]]:
    """Build an undirected adjacency map for elements in the same layer."""
    neighbors: dict[str, list[str]] = defaultdict(list)
    for rel in relationships:
        source_layer = element_layer.get(rel.source)
        target_layer = element_layer.get(rel.target)
        if source_layer is None or target_layer is None or source_layer != target_layer:
            continue
        neighbors[rel.source].append(rel.target)
        neighbors[rel.target].append(rel.source)
    return neighbors


def _connected_components(element_ids: list[str], neighbors: dict[str, list[str]]) -> list[list[str]]:
    """Return same-layer connected components, preserving input order."""
    remaining = set(element_ids)
    components: list[list[str]] = []

    for element_id in element_ids:
        if element_id not in remaining:
            continue

        component: list[str] = []
        stack = [element_id]
        remaining.remove(element_id)

        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in neighbors.get(current, []):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)

        components.append(component)

    return components


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _candidate_positions(anchor: tuple[int, int], direction: str, max_radius: int = 4) -> list[tuple[int, int]]:
    """
    Generate candidate cells extending from an anchor in one cardinal direction.

    We start with the direct adjacent cell and then widen slightly around the same side
    before expanding farther out.
    """
    row, col = anchor
    d_row, d_col = _DIRECTION_DELTAS[direction]
    candidates: list[tuple[int, int]] = []

    for distance in range(1, max_radius + 1):
        base_row = row + d_row * distance
        base_col = col + d_col * distance
        candidates.append((base_row, base_col))

        if direction in ("E", "W"):
            for spread in range(1, distance + 1):
                candidates.append((base_row - spread, base_col))
                candidates.append((base_row + spread, base_col))
        else:
            for spread in range(1, distance + 1):
                candidates.append((base_row, base_col - spread))
                candidates.append((base_row, base_col + spread))

    seen: set[tuple[int, int]] = set()
    ordered: list[tuple[int, int]] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def _score_position(
    element_id: str,
    candidate: tuple[int, int],
    anchor_id: str,
    direction: str,
    ctx: _LayerPlacementContext,
) -> float:
    """
    Score a candidate cell for an element.

    Higher is better:
    - close to already placed related elements
    - directly on the requested side of the current anchor
    - not too crowded compared with unrelated nodes
    """
    anchor_pos = ctx.positions[anchor_id]
    score = 0.0

    if _manhattan(candidate, anchor_pos) == 1:
        score += 30.0

    row_delta = candidate[0] - anchor_pos[0]
    col_delta = candidate[1] - anchor_pos[1]
    if direction == "E" and col_delta > 0:
        score += 20.0
    elif direction == "W" and col_delta < 0:
        score += 20.0
    elif direction == "N" and row_delta < 0:
        score += 20.0
    elif direction == "S" and row_delta > 0:
        score += 20.0

    for neighbor_id in ctx.neighbors_of(element_id):
        neighbor_pos = ctx.positions.get(neighbor_id)
        if neighbor_pos is None:
            continue
        distance = _manhattan(candidate, neighbor_pos)
        score += max(0.0, 18.0 - distance * 4.0)
        if neighbor_pos[0] == candidate[0] or neighbor_pos[1] == candidate[1]:
            score += 3.0

    for other_id, other_pos in ctx.positions.items():
        if other_id == element_id or other_id in ctx.neighbors_of(element_id):
            continue
        distance = _manhattan(candidate, other_pos)
        if distance == 1:
            score -= 10.0
        elif distance == 2:
            score -= 3.0

    related_positions = [
        ctx.positions[neighbor_id]
        for neighbor_id in ctx.neighbors_of(element_id)
        if neighbor_id in ctx.positions
    ]
    if related_positions:
        avg_row = sum(row for row, _ in related_positions) / len(related_positions)
        avg_col = sum(col for _, col in related_positions) / len(related_positions)
        score -= abs(candidate[0] - avg_row) * 1.5
        score -= abs(candidate[1] - avg_col) * 1.5

    return score


def _choose_best_position(
    element_id: str,
    anchor_id: str,
    preferred_direction: str,
    ctx: _LayerPlacementContext,
) -> tuple[int, int]:
    """Choose the best available cell for an element around an anchor."""
    best_candidate: tuple[int, int] | None = None
    best_score: float | None = None

    direction_priority = [preferred_direction] + [
        direction for direction in _DIRECTION_ORDER if direction != preferred_direction
    ]

    for direction in direction_priority:
        for candidate in _candidate_positions(ctx.positions[anchor_id], direction):
            if not ctx.is_free(candidate[0], candidate[1], moving_element=element_id):
                continue
            score = _score_position(element_id, candidate, anchor_id, direction, ctx)
            if best_score is None or score > best_score:
                best_score = score
                best_candidate = candidate

        if best_candidate is not None and direction == preferred_direction:
            break

    if best_candidate is None:
        anchor_row, anchor_col = ctx.positions[anchor_id]
        return (anchor_row, anchor_col + 1)
    return best_candidate


def _try_relocate_element(element_id: str, anchor_id: str, ctx: _LayerPlacementContext) -> None:
    """
    Re-evaluate an already placed element when a new anchor relationship becomes visible.

    This keeps placements provisional instead of locking them forever on first sight.
    """
    current_pos = ctx.positions[element_id]
    best_pos = current_pos
    best_score = _score_position(element_id, current_pos, anchor_id, "E", ctx)

    for direction in _DIRECTION_ORDER:
        for candidate in _candidate_positions(ctx.positions[anchor_id], direction, max_radius=3):
            if not ctx.is_free(candidate[0], candidate[1], moving_element=element_id):
                continue
            score = _score_position(element_id, candidate, anchor_id, direction, ctx)
            if score > best_score + 6.0:
                best_score = score
                best_pos = candidate

    if best_pos != current_pos:
        ctx.place(element_id, best_pos[0], best_pos[1])


def _place_component(component_ids: list[str], neighbors: dict[str, list[str]]) -> ComponentPlacement:
    """
    Place a connected component by graph expansion.

    The first element acts as the initial root. Every next placed element can in turn
    expand its own direct neighbors, which keeps the layout relationship-first.
    """
    root_id = component_ids[0]
    ctx = _LayerPlacementContext(
        element_ids=component_ids,
        same_layer_neighbors=neighbors,
    )
    ctx.place(root_id, 0, 0)
    ctx.queue.append(root_id)
    ctx.visited.add(root_id)

    while ctx.queue:
        current_id = ctx.queue.popleft()
        related_ids = [
            neighbor_id
            for neighbor_id in ctx.neighbors_of(current_id)
            if neighbor_id in component_ids
        ]

        related_ids.sort(
            key=lambda neighbor_id: (
                neighbor_id in ctx.positions,
                -len([n for n in ctx.neighbors_of(neighbor_id) if n in ctx.positions]),
                neighbor_id,
            )
        )

        for index, neighbor_id in enumerate(related_ids):
            preferred_direction = _DIRECTION_ORDER[index % len(_DIRECTION_ORDER)]
            if neighbor_id not in ctx.positions:
                row, col = _choose_best_position(
                    neighbor_id,
                    current_id,
                    preferred_direction,
                    ctx,
                )
                ctx.place(neighbor_id, row, col)
                if neighbor_id not in ctx.visited:
                    ctx.visited.add(neighbor_id)
                    ctx.queue.append(neighbor_id)
            else:
                _try_relocate_element(neighbor_id, current_id, ctx)

    return ComponentPlacement(positions=dict(ctx.positions))


def _normalize_component(component: ComponentPlacement) -> ComponentPlacement:
    """Shift a component so that its top-left corner starts at (0, 0)."""
    min_row, _, min_col, _ = component.bounds
    normalized = {
        element_id: (row - min_row, col - min_col)
        for element_id, (row, col) in component.positions.items()
    }
    return ComponentPlacement(positions=normalized)


def _pack_components(
    components: list[ComponentPlacement],
    width_cap: int,
) -> tuple[dict[str, tuple[int, int]], int]:
    """
    Pack normalized components into a layer using a simple shelf layout.

    The cap applies to whole components, not individual elements. That keeps the
    layout flexible while still preventing one infinitely wide strip.
    """
    packed_positions: dict[str, tuple[int, int]] = {}
    cursor_row = 0
    cursor_col = 0
    shelf_height = 0

    for component in components:
        min_row, max_row, min_col, max_col = component.bounds
        comp_height = max_row - min_row + 1
        comp_width = max_col - min_col + 1

        effective_cap = max(width_cap, comp_width)
        if cursor_col > 0 and cursor_col + comp_width > effective_cap:
            cursor_row += shelf_height + 2
            cursor_col = 0
            shelf_height = 0

        for element_id, (row, col) in component.positions.items():
            packed_positions[element_id] = (cursor_row + row, cursor_col + col)

        cursor_col += comp_width + 2
        shelf_height = max(shelf_height, comp_height)

    total_rows = cursor_row + shelf_height
    return packed_positions, total_rows


def build_smart_grid(
    layer_elements: dict[str, list],
    layer_order: list[str],
    relationships: list,
    element_layer: dict[str, str],
    max_cols_per_row: int = 6,
) -> tuple[PlacementGrid, set[int]]:
    """
    Build a sparse grid through graph expansion instead of fixed row packing.

    For each layer:
    1. split into connected components
    2. use the first element as the root of each component
    3. place direct relations around each current root in W/E/N/S
    4. expand iteratively, allowing local relocation when a better side appears
    5. pack completed components into the layer with a soft width cap
    """
    grid = PlacementGrid()
    same_layer_neighbors = _build_same_layer_neighbor_map(relationships, element_layer)

    active_layers = [layer_id for layer_id in layer_order if layer_elements.get(layer_id)]
    layer_boundary_rows: set[int] = set()
    row_offset = 0

    for layer_id in active_layers:
        items = layer_elements.get(layer_id, [])
        element_ids = [item.id for item in items]
        components = _connected_components(element_ids, same_layer_neighbors)

        placed_components = [
            _normalize_component(_place_component(component_ids, same_layer_neighbors))
            for component_ids in components
        ]

        packed_positions, layer_height = _pack_components(
            placed_components,
            width_cap=max(4, max_cols_per_row),
        )

        layer_boundary_rows.add(row_offset)
        for element_id in element_ids:
            local_row, local_col = packed_positions[element_id]
            grid.place(row_offset + local_row, local_col, element_id)

        row_offset += max(1, layer_height)

    return grid, layer_boundary_rows


@dataclass
class GridMetrics:
    col_widths: dict[int, int]
    row_heights: dict[int, int]
    cfg: LayoutConfig
    layer_boundary_rows: set[int] | None = None

    def __post_init__(self):
        if self.layer_boundary_rows is None:
            object.__setattr__(self, "layer_boundary_rows", set())

    def x_of(self, col: int) -> int:
        x = self.cfg.margin_left
        for current_col in range(col):
            x += self.col_widths.get(current_col, self.cfg.node_w) + self.cfg.h_gap
        return x

    def y_of(self, row: int) -> int:
        y = self.cfg.margin_top
        for current_row in range(row):
            height = self.row_heights.get(current_row, self.cfg.node_h)
            gap = (
                self.cfg.layer_v_gap
                if (current_row + 1) in self.layer_boundary_rows
                else self.cfg.row_v_gap
            )
            y += height + gap
        return y


def compute_grid_metrics(
    grid: PlacementGrid,
    node_sizes: dict[str, tuple[int, int]],
    cfg: LayoutConfig,
    layer_boundary_rows: set[int] | None = None,
) -> GridMetrics:
    col_widths: dict[int, int] = defaultdict(int)
    row_heights: dict[int, int] = defaultdict(int)

    for cell in grid.cells:
        width, height = node_sizes.get(cell.element_id, (cfg.node_w, cfg.node_h))
        col_widths[cell.col] = max(col_widths[cell.col], width)
        row_heights[cell.row] = max(row_heights[cell.row], height)

    return GridMetrics(
        col_widths=dict(col_widths),
        row_heights=dict(row_heights),
        cfg=cfg,
        layer_boundary_rows=layer_boundary_rows or set(),
    )
