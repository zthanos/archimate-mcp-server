from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .config import LayoutConfig


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GridCell:
    row: int
    col: int
    element_id: str


@dataclass
class PlacementGrid:
    """
    Sparse grid where:
      row = ArchiMate layer index (strict: layer 0, 1, 2 ...)
      col = horizontal position within a layer

    Each (row, col) can hold at most one element.
    """
    cells: list[GridCell] = field(default_factory=list)
    _occupied: dict[tuple[int, int], str] = field(default_factory=dict, repr=False)
    _element_pos: dict[str, tuple[int, int]] = field(default_factory=dict, repr=False)

    def place(self, row: int, col: int, element_id: str) -> int:
        """Place element at (row, col), shifting right until free. Returns actual col."""
        while (row, col) in self._occupied:
            col += 1
        self._occupied[(row, col)] = element_id
        self._element_pos[element_id] = (row, col)
        self.cells.append(GridCell(row=row, col=col, element_id=element_id))
        return col

    def _update_pos(self, element_id: str, row: int, col: int) -> None:
        """Update the position index after a cell move."""
        self._element_pos[element_id] = (row, col)

    def col_of(self, element_id: str) -> int | None:
        pos = self._element_pos.get(element_id)
        return pos[1] if pos else None

    def row_of(self, element_id: str) -> int | None:
        pos = self._element_pos.get(element_id)
        return pos[0] if pos else None

    def elements_in_row(self, row: int) -> list[GridCell]:
        return sorted([c for c in self.cells if c.row == row], key=lambda c: c.col)

    def is_occupied(self, row: int, col: int) -> bool:
        return (row, col) in self._occupied

    @property
    def max_col(self) -> int:
        return max((c.col for c in self.cells), default=0)

    @property
    def max_row(self) -> int:
        return max((c.row for c in self.cells), default=0)


# ---------------------------------------------------------------------------
# Cross-layer arrow analysis
# ---------------------------------------------------------------------------

@dataclass
class CrossLayerArrow:
    source_id: str
    target_id: str
    source_row: int
    target_row: int
    # Filled in after placement
    source_col: int | None = None
    target_col: int | None = None

    @property
    def passes_through_rows(self) -> list[int]:
        """Rows this arrow passes through (exclusive of src/tgt row)."""
        lo = min(self.source_row, self.target_row)
        hi = max(self.source_row, self.target_row)
        return list(range(lo + 1, hi))


def _build_cross_layer_arrows(
    relationships: list,
    element_layer: dict[str, str],
    layer_order: list[str],
) -> list[CrossLayerArrow]:
    layer_row = {lid: i for i, lid in enumerate(layer_order)}
    arrows: list[CrossLayerArrow] = []
    for rel in relationships:
        sl = element_layer.get(rel.source)
        tl = element_layer.get(rel.target)
        if not sl or not tl or sl == tl:
            continue
        sr = layer_row.get(sl)
        tr = layer_row.get(tl)
        if sr is None or tr is None:
            continue
        arrows.append(CrossLayerArrow(
            source_id=rel.source,
            target_id=rel.target,
            source_row=sr,
            target_row=tr,
        ))
    return arrows


# ---------------------------------------------------------------------------
# Smart placement algorithm
# ---------------------------------------------------------------------------

def build_smart_grid(
    layer_elements: dict[str, list],
    layer_order: list[str],
    relationships: list,
    element_layer: dict[str, str],
    max_cols_per_row: int = 6,
) -> tuple[PlacementGrid, set[int]]:
    """
    Place elements in a smart grid with:

    1. Row wrapping: if a layer has more than max_cols_per_row elements,
       they wrap into multiple sub-rows within the same layer band.
    2. Column alignment: elements connected cross-layer prefer the same column.
    3. Collision avoidance: shift elements that block cross-layer arrows.
    """
    grid = PlacementGrid()

    # Build active layer order (skip empty layers)
    active_layers = [lid for lid in layer_order if layer_elements.get(lid)]

    # Assign row ranges per layer — each layer gets ceil(n/max_cols) rows
    layer_row_start: dict[str, int] = {}
    layer_row_count: dict[str, int] = {}
    current_row = 0
    for lid in active_layers:
        n = len(layer_elements.get(lid, []))
        n_rows = max(1, (n + max_cols_per_row - 1) // max_cols_per_row)
        layer_row_start[lid] = current_row
        layer_row_count[lid] = n_rows
        current_row += n_rows

    # The first row of each layer is a "layer boundary"
    # (used by GridMetrics to apply layer_v_gap instead of row_v_gap)
    layer_boundary_rows: set[int] = {r for r in layer_row_start.values()}

    # element_layer → row index (first row of its layer)
    element_row: dict[str, int] = {}
    for el_id, lid in element_layer.items():
        if lid in layer_row_start:
            element_row[el_id] = layer_row_start[lid]

    # Cross-layer neighbor map (for column inheritance)
    cross_layer_neighbors: dict[str, list[str]] = defaultdict(list)
    for rel in relationships:
        sr = element_row.get(rel.source)
        tr = element_row.get(rel.target)
        if sr is not None and tr is not None and sr != tr:
            cross_layer_neighbors[rel.source].append(rel.target)
            cross_layer_neighbors[rel.target].append(rel.source)

    # --- Pass 1: Place elements layer by layer with wrapping ---
    for layer_id in active_layers:
        items = layer_elements.get(layer_id, [])
        row_start = layer_row_start[layer_id]
        n_rows = layer_row_count[layer_id]

        # Sort: cross-layer connected first for better alignment
        def sort_key(el):
            neighbors = cross_layer_neighbors.get(el.id, [])
            placed = [n for n in neighbors if grid.col_of(n) is not None]
            return (-len(placed), -len(neighbors), el.name)

        sorted_items = sorted(items, key=sort_key)

        for idx, element in enumerate(sorted_items):
            # Distribute across sub-rows: fill row by row
            sub_row = row_start + (idx // max_cols_per_row)
            preferred = _preferred_col(element.id, cross_layer_neighbors, grid, sub_row)
            actual_col = grid.place(sub_row, preferred, element.id)
            # Update element_row to actual sub-row for cross-layer arrow logic
            element_row[element.id] = sub_row

    # --- Pass 2: Collision avoidance ---
    cross_arrows = _build_cross_layer_arrows(relationships, element_layer, active_layers)

    for arrow in cross_arrows:
        src_col = grid.col_of(arrow.source_id)
        tgt_col = grid.col_of(arrow.target_id)
        if src_col is None or tgt_col is None:
            continue

        arrow_cols = set(range(min(src_col, tgt_col), max(src_col, tgt_col) + 1))

        src_lid = element_layer.get(arrow.source_id)
        tgt_lid = element_layer.get(arrow.target_id)
        if not src_lid or not tgt_lid:
            continue
        src_row = layer_row_start.get(src_lid)
        tgt_row = layer_row_start.get(tgt_lid)
        if src_row is None or tgt_row is None:
            continue

        lo_row = min(src_row, tgt_row)
        hi_row = max(src_row, tgt_row)

        for mid_row in range(lo_row + 1, hi_row):
            for col in arrow_cols:
                if not grid.is_occupied(mid_row, col):
                    continue
                blocking_id = grid._occupied[(mid_row, col)]
                if blocking_id in (arrow.source_id, arrow.target_id):
                    continue
                new_col = max(arrow_cols) + 1
                grid._occupied.pop((mid_row, col))
                for i, cell in enumerate(grid.cells):
                    if cell.element_id == blocking_id:
                        grid.cells[i] = GridCell(row=mid_row, col=new_col, element_id=blocking_id)
                        break
                grid._occupied[(mid_row, new_col)] = blocking_id
                grid._update_pos(blocking_id, mid_row, new_col)

    # --- Pass 3: Same-row reordering ---
    same_row_neighbors: dict[str, list[str]] = defaultdict(list)
    for rel in relationships:
        sr = element_row.get(rel.source)
        tr = element_row.get(rel.target)
        if sr is not None and tr is not None and sr == tr:
            same_row_neighbors[rel.source].append(rel.target)
            same_row_neighbors[rel.target].append(rel.source)

    for layer_id in active_layers:
        start_row = layer_row_start[layer_id]
        n_rows = layer_row_count[layer_id]
        for row in range(start_row, start_row + n_rows):
            cells = grid.elements_in_row(row)
            if len(cells) < 3:
                continue

            element_ids = [c.element_id for c in cells]

            def same_row_degree(eid):
                return len([n for n in same_row_neighbors.get(eid, []) if n in element_ids])

            center = max(element_ids, key=same_row_degree)
            if same_row_degree(center) == 0:
                continue

            neighbors = [n for n in same_row_neighbors.get(center, []) if n in element_ids]
            others = [e for e in element_ids if e != center and e not in neighbors]
            left_neighbors  = neighbors[:len(neighbors) // 2]
            right_neighbors = neighbors[len(neighbors) // 2:]
            new_order = (others[:len(others) // 2] + left_neighbors +
                         [center] + right_neighbors + others[len(others) // 2:])

            grid._occupied = {k: v for k, v in grid._occupied.items() if k[0] != row}
            for new_col, eid in enumerate(new_order):
                grid._occupied[(row, new_col)] = eid
                grid._update_pos(eid, row, new_col)
                for i, cell in enumerate(grid.cells):
                    if cell.element_id == eid:
                        grid.cells[i] = GridCell(row=row, col=new_col, element_id=eid)
                        break

    return grid, layer_boundary_rows


def _preferred_col(
    element_id: str,
    cross_layer_neighbors: dict[str, list[str]],
    grid: PlacementGrid,
    row: int,
    same_row_neighbors: dict[str, list[str]] | None = None,
) -> int:
    neighbors = cross_layer_neighbors.get(element_id, [])
    placed_cols = [grid.col_of(n) for n in neighbors if grid.col_of(n) is not None]

    # Also consider same-row (same-layer) neighbors for spread
    same_row_placed = []
    if same_row_neighbors:
        sr_neighbors = same_row_neighbors.get(element_id, [])
        same_row_placed = [grid.col_of(n) for n in sr_neighbors if grid.col_of(n) is not None]

    if not placed_cols and not same_row_placed:
        # No neighbors placed yet — use next free col in this row
        occupied = {c.col for c in grid.cells if c.row == row}
        col = 0
        while col in occupied:
            col += 1
        return col

    if placed_cols:
        # Align with cross-layer neighbor (median)
        placed_cols.sort()
        preferred = placed_cols[len(placed_cols) // 2]
        # If a same-row neighbor is right next to us, spread by 1 extra col
        if same_row_placed:
            for sr_col in same_row_placed:
                if abs(preferred - sr_col) <= 1:
                    preferred = max(same_row_placed) + 2  # leave a gap
        return preferred

    # Only same-row neighbors placed — go next to them with a gap
    return max(same_row_placed) + 2


# ---------------------------------------------------------------------------
# Grid → pixel coordinates
# ---------------------------------------------------------------------------

@dataclass
class GridMetrics:
    col_widths: dict[int, int]
    row_heights: dict[int, int]
    cfg: LayoutConfig
    layer_boundary_rows: set[int] = None  # rows that start a new layer

    def __post_init__(self):
        if self.layer_boundary_rows is None:
            object.__setattr__(self, 'layer_boundary_rows', set())

    def x_of(self, col: int) -> int:
        x = self.cfg.margin_left
        for c in range(col):
            x += self.col_widths.get(c, self.cfg.node_w) + self.cfg.h_gap
        return x

    def y_of(self, row: int) -> int:
        y = self.cfg.margin_top
        for r in range(row):
            h = self.row_heights.get(r, self.cfg.node_h)
            # Use layer_v_gap between layers, row_v_gap between wrapped sub-rows
            gap = self.cfg.layer_v_gap if (r + 1) in self.layer_boundary_rows else self.cfg.row_v_gap
            y += h + gap
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
        w, h = node_sizes.get(cell.element_id, (cfg.node_w, cfg.node_h))
        col_widths[cell.col]  = max(col_widths[cell.col],  w)
        row_heights[cell.row] = max(row_heights[cell.row], h)

    return GridMetrics(
        col_widths=dict(col_widths),
        row_heights=dict(row_heights),
        cfg=cfg,
        layer_boundary_rows=layer_boundary_rows or set(),
    )