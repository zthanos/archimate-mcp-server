from __future__ import annotations

from types import SimpleNamespace

from archimate_mcp.grid import build_smart_grid


def _element(element_id: str, name: str):
    return SimpleNamespace(id=element_id, name=name)


def _relationship(source: str, target: str):
    return SimpleNamespace(source=source, target=target)


def _pos(grid, element_id: str) -> tuple[int, int]:
    row = grid.row_of(element_id)
    col = grid.col_of(element_id)
    assert row is not None
    assert col is not None
    return row, col


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def test_build_smart_grid_keeps_related_chain_compact() -> None:
    layer_elements = {
        "application": [
            _element("a", "A"),
            _element("b", "B"),
            _element("c", "C"),
            _element("d", "D"),
        ]
    }
    relationships = [
        _relationship("a", "b"),
        _relationship("b", "c"),
    ]
    element_layer = {element.id: "application" for element in layer_elements["application"]}

    grid, _ = build_smart_grid(
        layer_elements=layer_elements,
        layer_order=["application"],
        relationships=relationships,
        element_layer=element_layer,
        max_cols_per_row=8,
    )

    pos_a = _pos(grid, "a")
    pos_b = _pos(grid, "b")
    pos_c = _pos(grid, "c")

    assert _manhattan(pos_a, pos_b) <= 2
    assert _manhattan(pos_b, pos_c) <= 2


def test_build_smart_grid_places_relationship_clusters_together() -> None:
    layer_elements = {
        "application": [
            _element("a", "A"),
            _element("b", "B"),
            _element("c", "C"),
            _element("d", "D"),
            _element("e", "E"),
            _element("f", "F"),
        ]
    }
    relationships = [
        _relationship("a", "b"),
        _relationship("b", "c"),
        _relationship("d", "e"),
    ]
    element_layer = {element.id: "application" for element in layer_elements["application"]}

    grid, _ = build_smart_grid(
        layer_elements=layer_elements,
        layer_order=["application"],
        relationships=relationships,
        element_layer=element_layer,
        max_cols_per_row=5,
    )

    pos_a = _pos(grid, "a")
    pos_b = _pos(grid, "b")
    pos_c = _pos(grid, "c")
    pos_d = _pos(grid, "d")
    pos_e = _pos(grid, "e")

    assert max(_manhattan(pos_a, pos_b), _manhattan(pos_b, pos_c)) <= 2
    assert _manhattan(pos_d, pos_e) <= 2
    assert _manhattan(pos_a, pos_d) >= 2
