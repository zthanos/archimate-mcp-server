from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

from .models import Node


class Segment(NamedTuple):
    """An axis-aligned segment occupying a lane."""

    x1: int
    y1: int
    x2: int
    y2: int
    rel_id: str


def _segments_overlap(a1: int, a2: int, b1: int, b2: int, margin: int = 4) -> bool:
    """Do two 1-D intervals overlap with a small guard margin?"""
    lo_a, hi_a = min(a1, a2), max(a1, a2)
    lo_b, hi_b = min(b1, b2), max(b1, b2)
    return lo_a - margin < hi_b and hi_a + margin > lo_b


@dataclass
class _LanePool:
    """
    A pool of parallel lanes within a band.

    Horizontal pool: lanes have fixed y, segments extend in x.
    Vertical pool: lanes have fixed x, segments extend in y.
    """

    is_horizontal: bool
    base: int
    step: int
    max_lanes: int = 24
    _occupancy: dict[int, list[Segment]] = field(default_factory=dict)

    def _lane_indices(self):
        yield 0
        for i in range(1, self.max_lanes):
            yield i
            yield -i

    def _lane_coord(self, lane_idx: int) -> int:
        """Convert a lane index (0, +/-1, +/-2, ...) to a pixel coordinate."""
        if lane_idx == 0:
            return self.base
        offset = (abs(lane_idx) - 1) * self.step + self.step // 2
        return self.base + offset if lane_idx > 0 else self.base - offset

    def _is_free(self, lane_idx: int, seg_lo: int, seg_hi: int) -> bool:
        """True if no existing segment in lane_idx overlaps the requested interval."""
        for existing in self._occupancy.get(lane_idx, []):
            if self.is_horizontal:
                if _segments_overlap(existing.x1, existing.x2, seg_lo, seg_hi):
                    return False
            else:
                if _segments_overlap(existing.y1, existing.y2, seg_lo, seg_hi):
                    return False
        return True

    def _hits_node(
        self,
        coord: int,
        seg_lo: int,
        seg_hi: int,
        obstacles: list[Node],
        skip_ids: frozenset[str],
        padding: int,
    ) -> bool:
        """True if the proposed lane segment intersects any obstacle node."""
        for node in obstacles:
            if node.id in skip_ids:
                continue
            left = node.x - padding
            right = node.x + node.w + padding
            top = node.y - padding
            bottom = node.y + node.h + padding

            if self.is_horizontal:
                if not (top <= coord <= bottom):
                    continue
                if _segments_overlap(seg_lo, seg_hi, left, right):
                    return True
            else:
                if not (left <= coord <= right):
                    continue
                if _segments_overlap(seg_lo, seg_hi, top, bottom):
                    return True
        return False

    def candidate_coords(self) -> list[int]:
        """Return candidate lane coordinates ordered by preference."""
        return [self._lane_coord(lane_idx) for lane_idx in self._lane_indices()]

    def can_allocate_at(
        self,
        coord: int,
        seg_lo: int,
        seg_hi: int,
        obstacles: list[Node],
        skip_ids: frozenset[str],
        padding: int,
    ) -> bool:
        """Return True if the requested coordinate is available for the segment."""
        for lane_idx in self._lane_indices():
            if self._lane_coord(lane_idx) != coord:
                continue
            return (
                self._is_free(lane_idx, seg_lo, seg_hi)
                and not self._hits_node(coord, seg_lo, seg_hi, obstacles, skip_ids, padding)
            )
        return False

    def reserve_at(self, coord: int, seg_lo: int, seg_hi: int, rel_id: str) -> bool:
        """Reserve a specific lane coordinate if it belongs to this pool."""
        for lane_idx in self._lane_indices():
            if self._lane_coord(lane_idx) != coord:
                continue
            seg = (
                Segment(seg_lo, coord, seg_hi, coord, rel_id)
                if self.is_horizontal
                else Segment(coord, seg_lo, coord, seg_hi, rel_id)
            )
            self._occupancy.setdefault(lane_idx, []).append(seg)
            return True
        return False

    def allocate(
        self,
        seg_lo: int,
        seg_hi: int,
        rel_id: str,
        obstacles: list[Node],
        skip_ids: frozenset[str],
        padding: int,
    ) -> int | None:
        """
        Find the first free lane and reserve it.

        Returns the pixel coordinate of the lane, or None if all lanes are full.
        """
        for coord in self.candidate_coords():
            if self.can_allocate_at(coord, seg_lo, seg_hi, obstacles, skip_ids, padding):
                self.reserve_at(coord, seg_lo, seg_hi, rel_id)
                return coord
        return None


@dataclass
class LaneAllocator:
    """
    Manages lane pools across the diagram.

    Horizontal bands are identified by (row_top, row_bottom).
    Vertical bands are identified by (col_left, col_right).
    """

    h_step: int = 20
    v_step: int = 20
    padding: int = 8
    _h_pools: dict[tuple[int, int], _LanePool] = field(default_factory=dict)
    _v_pools: dict[tuple[int, int], _LanePool] = field(default_factory=dict)

    def _h_pool(self, band: tuple[int, int]) -> _LanePool:
        if band not in self._h_pools:
            base = (band[0] + band[1]) // 2
            self._h_pools[band] = _LanePool(is_horizontal=True, base=base, step=self.h_step)
        return self._h_pools[band]

    def _v_pool(self, band: tuple[int, int]) -> _LanePool:
        if band not in self._v_pools:
            base = (band[0] + band[1]) // 2
            self._v_pools[band] = _LanePool(is_horizontal=False, base=base, step=self.v_step)
        return self._v_pools[band]

    def get_h_lane(
        self,
        band: tuple[int, int],
        x_lo: int,
        x_hi: int,
        rel_id: str,
        obstacles: list[Node],
        skip_ids: frozenset[str],
    ) -> int | None:
        return self._h_pool(band).allocate(
            x_lo, x_hi, rel_id, obstacles, skip_ids, self.padding
        )

    def iter_h_lanes(self, band: tuple[int, int]) -> list[int]:
        return self._h_pool(band).candidate_coords()

    def can_use_h_lane(
        self,
        band: tuple[int, int],
        y: int,
        x_lo: int,
        x_hi: int,
        obstacles: list[Node],
        skip_ids: frozenset[str],
    ) -> bool:
        return self._h_pool(band).can_allocate_at(
            y, x_lo, x_hi, obstacles, skip_ids, self.padding
        )

    def reserve_h_lane(
        self,
        band: tuple[int, int],
        y: int,
        x_lo: int,
        x_hi: int,
        rel_id: str,
    ) -> bool:
        return self._h_pool(band).reserve_at(y, x_lo, x_hi, rel_id)

    def get_v_lane(
        self,
        band: tuple[int, int],
        y_lo: int,
        y_hi: int,
        rel_id: str,
        obstacles: list[Node],
        skip_ids: frozenset[str],
    ) -> int | None:
        return self._v_pool(band).allocate(
            y_lo, y_hi, rel_id, obstacles, skip_ids, self.padding
        )

    def iter_v_lanes(self, band: tuple[int, int]) -> list[int]:
        return self._v_pool(band).candidate_coords()

    def can_use_v_lane(
        self,
        band: tuple[int, int],
        x: int,
        y_lo: int,
        y_hi: int,
        obstacles: list[Node],
        skip_ids: frozenset[str],
    ) -> bool:
        return self._v_pool(band).can_allocate_at(
            x, y_lo, y_hi, obstacles, skip_ids, self.padding
        )

    def reserve_v_lane(
        self,
        band: tuple[int, int],
        x: int,
        y_lo: int,
        y_hi: int,
        rel_id: str,
    ) -> bool:
        return self._v_pool(band).reserve_at(x, y_lo, y_hi, rel_id)
