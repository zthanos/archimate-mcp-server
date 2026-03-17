from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


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

    def place(self, row: int, col: int, element_id: str) -> int:
        """Place element at (row, col), shifting right until free. Returns actual col."""
        while (row, col) in self._occupied:
            col += 1
        self._occupied[(row, col)] = element_id
        self.cells.append(GridCell(row=row, col=col, element_id=element_id))
        return col

    def col_of(self, element_id: str) -> int | None:
        for cell in self.cells:
            if cell.element_id == element_id:
                return cell.col
        return None

    def row_of(self, element_id: str) -> int | None:
        for cell in self.cells:
            if cell.element_id == element_id:
                return cell.row
        return None

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
) -> PlacementGrid:
    """
    Place elements in a smart grid with:

    1. Strict row-per-layer (layer N always = row N in output, skipping empty layers)
    2. Column alignment: elements connected cross-layer prefer the same column
    3. Collision avoidance: if a cross-layer arrow passes through a cell occupied
       by an unrelated element, shift that element right
    """
    grid = PlacementGrid()

    # Build active layer order (skip empty layers)
    active_layers = [lid for lid in layer_order if layer_elements.get(lid)]
    layer_to_row = {lid: i for i, lid in enumerate(active_layers)}

    # Remap element_layer to active row index
    element_row: dict[str, int] = {}
    for el_id, lid in element_layer.items():
        row = layer_to_row.get(lid)
        if row is not None:
            element_row[el_id] = row

    # Cross-layer neighbor map (for column inheritance)
    cross_layer_neighbors: dict[str, list[str]] = defaultdict(list)
    for rel in relationships:
        sr = element_row.get(rel.source)
        tr = element_row.get(rel.target)
        if sr is not None and tr is not None and sr != tr:
            cross_layer_neighbors[rel.source].append(rel.target)
            cross_layer_neighbors[rel.target].append(rel.source)

    # --- Pass 1: Place elements layer by layer ---
    for layer_id in active_layers:
        row = layer_to_row[layer_id]
        items = layer_elements.get(layer_id, [])

        # Sort: elements with already-placed neighbors first, then most-connected
        def sort_key(el):
            neighbors = cross_layer_neighbors.get(el.id, [])
            placed = [n for n in neighbors if grid.col_of(n) is not None]
            return (-len(placed), -len(neighbors), el.name)

        for element in sorted(items, key=sort_key):
            preferred = _preferred_col(element.id, cross_layer_neighbors, grid, row)
            grid.place(row, preferred, element.id)

    # --- Pass 2: Collision avoidance ---
    # For each cross-layer arrow, check if it passes through an occupied cell
    # in an intermediate row at the same column. If so, shift the intermediate
    # element right to open up that column.
    cross_arrows = _build_cross_layer_arrows(relationships, element_layer, active_layers)

    for arrow in cross_arrows:
        src_col = grid.col_of(arrow.source_id)
        tgt_col = grid.col_of(arrow.target_id)
        if src_col is None or tgt_col is None:
            continue

        # Arrow runs vertically between src_col and tgt_col
        # Check every intermediate row at those columns
        arrow_cols = set(range(min(src_col, tgt_col), max(src_col, tgt_col) + 1))

        # Remap pass-through rows to active layer rows
        src_lid = element_layer.get(arrow.source_id)
        tgt_lid = element_layer.get(arrow.target_id)
        if not src_lid or not tgt_lid:
            continue
        src_row = layer_to_row.get(src_lid)
        tgt_row = layer_to_row.get(tgt_lid)
        if src_row is None or tgt_row is None:
            continue

        lo_row = min(src_row, tgt_row)
        hi_row = max(src_row, tgt_row)
        through_rows = range(lo_row + 1, hi_row)

        for mid_row in through_rows:
            for col in arrow_cols:
                if not grid.is_occupied(mid_row, col):
                    continue
                blocking_id = grid._occupied[(mid_row, col)]
                # Only shift if it's not the source or target of THIS arrow
                if blocking_id in (arrow.source_id, arrow.target_id):
                    continue
                # Shift blocking element right until clear of arrow columns
                new_col = max(arrow_cols) + 1
                # Remove old placement
                grid._occupied.pop((mid_row, col))
                for i, cell in enumerate(grid.cells):
                    if cell.element_id == blocking_id:
                        grid.cells[i] = GridCell(row=mid_row, col=new_col, element_id=blocking_id)
                        break
                grid._occupied[(mid_row, new_col)] = blocking_id

    return grid


def _preferred_col(
    element_id: str,
    cross_layer_neighbors: dict[str, list[str]],
    grid: PlacementGrid,
    row: int,
) -> int:
    neighbors = cross_layer_neighbors.get(element_id, [])
    placed_cols = [grid.col_of(n) for n in neighbors if grid.col_of(n) is not None]

    if not placed_cols:
        # No neighbors placed yet — use next free col in this row
        occupied = {c.col for c in grid.cells if c.row == row}
        col = 0
        while col in occupied:
            col += 1
        return col

    # Median of neighbor columns
    placed_cols.sort()
    return placed_cols[len(placed_cols) // 2]


# ---------------------------------------------------------------------------
# Grid → pixel coordinates
# ---------------------------------------------------------------------------

@dataclass
class GridMetrics:
    col_widths: dict[int, int]
    row_heights: dict[int, int]
    h_gap: int = 40
    v_gap: int = 160
    margin_left: int = 80
    margin_top: int = 60

    def x_of(self, col: int) -> int:
        x = self.margin_left
        for c in range(col):
            x += self.col_widths.get(c, 200) + self.h_gap
        return x

    def y_of(self, row: int) -> int:
        y = self.margin_top
        for r in range(row):
            y += self.row_heights.get(r, 60) + self.v_gap
        return y


def compute_grid_metrics(
    grid: PlacementGrid,
    node_sizes: dict[str, tuple[int, int]],
    h_gap: int = 40,
    v_gap: int = 160,
    margin_left: int = 80,
    margin_top: int = 60,
) -> GridMetrics:
    col_widths: dict[int, int] = defaultdict(int)
    row_heights: dict[int, int] = defaultdict(int)

    for cell in grid.cells:
        w, h = node_sizes.get(cell.element_id, (200, 60))
        col_widths[cell.col] = max(col_widths[cell.col], w)
        row_heights[cell.row] = max(row_heights[cell.row], h)

    return GridMetrics(
        col_widths=dict(col_widths),
        row_heights=dict(row_heights),
        h_gap=h_gap,
        v_gap=v_gap,
        margin_left=margin_left,
        margin_top=margin_top,
    )