"""Warehouse grid: a 2D matrix of cells, parsed from an ASCII layout.

Coordinates are (x, y) with x = column and y = row, origin at the top-left.
The grid is stored row-major: ``cells[y][x]``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum

Pos = tuple[int, int]

# 4-connected movement: right, down, left, up. The order is fixed so that
# every search expands neighbours in the same order (determinism).
EAST, SOUTH, WEST, NORTH = (1, 0), (0, 1), (-1, 0), (0, -1)
DIRECTIONS: tuple[Pos, ...] = (EAST, SOUTH, WEST, NORTH)

# Lane overlay characters. A move a -> b in direction d is legal only if both
# a and b allow d. Cells without a lane allow every direction.
#   ^ / v  one-way vertical aisle
#   < / >  one-way cross aisle; vertical moves still allowed (intersections)
LANE_CHARS: dict[str, frozenset[Pos]] = {
    "^": frozenset({NORTH}),
    "v": frozenset({SOUTH}),
    "<": frozenset({WEST, NORTH, SOUTH}),
    ">": frozenset({EAST, NORTH, SOUTH}),
}


class Cell(StrEnum):
    FLOOR = "."
    WALL = "#"
    OBSTACLE = "X"
    SHELF = "S"
    PACK = "P"
    HOME = "H"

    @property
    def walkable(self) -> bool:
        return self in (Cell.FLOOR, Cell.PACK, Cell.HOME)


@dataclass
class Shelf:
    id: int
    pos: Pos
    access: Pos  # the floor cell a robot stands on to pick from this shelf


@dataclass
class Warehouse:
    width: int
    height: int
    cells: list[list[Cell]]
    shelves: list[Shelf] = field(default_factory=list)
    pack_stations: list[Pos] = field(default_factory=list)
    homes: list[Pos] = field(default_factory=list)
    lanes: dict[Pos, frozenset[Pos]] = field(default_factory=dict)

    @classmethod
    def from_ascii(cls, layout: str | list[str], lanes: list[str] | None = None) -> Warehouse:
        rows = layout if isinstance(layout, list) else layout.strip("\n").splitlines()
        if not rows:
            raise ValueError("layout is empty")
        width = len(rows[0])
        if any(len(r) != width for r in rows):
            raise ValueError("every layout row must have the same width")

        try:
            cells = [[Cell(ch) for ch in row] for row in rows]
        except ValueError as exc:
            raise ValueError(f"unknown cell character in layout: {exc}") from exc

        wh = cls(width=width, height=len(rows), cells=cells)
        if lanes is not None:
            if len(lanes) != len(rows) or any(len(r) != width for r in lanes):
                raise ValueError("lane overlay must match the layout dimensions")
            for y, lane_row in enumerate(lanes):
                for x, ch in enumerate(lane_row):
                    if ch in LANE_CHARS:
                        wh.lanes[(x, y)] = LANE_CHARS[ch]
                    elif ch != ".":
                        raise ValueError(f"unknown lane character {ch!r}")
        for y, row in enumerate(cells):
            for x, cell in enumerate(row):
                if cell is Cell.PACK:
                    wh.pack_stations.append((x, y))
                elif cell is Cell.HOME:
                    wh.homes.append((x, y))

        for y, row in enumerate(cells):
            for x, cell in enumerate(row):
                if cell is Cell.SHELF:
                    access = wh._access_cell((x, y))
                    if access is None:
                        raise ValueError(f"shelf at {(x, y)} has no walkable neighbour")
                    wh.shelves.append(Shelf(id=len(wh.shelves), pos=(x, y), access=access))

        if not wh.pack_stations:
            raise ValueError("layout needs at least one pack station (P)")
        return wh

    def in_bounds(self, pos: Pos) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def cell(self, pos: Pos) -> Cell:
        x, y = pos
        return self.cells[y][x]

    def walkable(self, pos: Pos) -> bool:
        return self.in_bounds(pos) and self.cell(pos).walkable

    def allows(self, pos: Pos, direction: Pos) -> bool:
        lane = self.lanes.get(pos)
        return lane is None or direction in lane

    def neighbors(self, pos: Pos) -> Iterator[Pos]:
        """Cells reachable from ``pos`` in one legal move."""
        x, y = pos
        for dx, dy in DIRECTIONS:
            nxt = (x + dx, y + dy)
            if self.walkable(nxt) and self.allows(pos, (dx, dy)) and self.allows(nxt, (dx, dy)):
                yield nxt

    def predecessors(self, pos: Pos) -> Iterator[Pos]:
        """Cells from which ``pos`` is reachable in one legal move."""
        x, y = pos
        for dx, dy in DIRECTIONS:
            prev = (x - dx, y - dy)
            if self.walkable(prev) and self.allows(prev, (dx, dy)) and self.allows(pos, (dx, dy)):
                yield prev

    def _access_cell(self, shelf: Pos) -> Pos | None:
        # Prefer plain floor so robots don't pick while parked on a station.
        candidates = [
            (shelf[0] + dx, shelf[1] + dy)
            for dx, dy in DIRECTIONS
            if self.walkable((shelf[0] + dx, shelf[1] + dy))
        ]
        floor = [c for c in candidates if self.cell(c) is Cell.FLOOR]
        best = floor or candidates
        return best[0] if best else None

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "rows": ["".join(c.value for c in row) for row in self.cells],
            "shelves": [{"id": s.id, "pos": s.pos, "access": s.access} for s in self.shelves],
            "pack_stations": self.pack_stations,
            "homes": self.homes,
            "lanes": {f"{x},{y}": sorted(d) for (x, y), d in self.lanes.items()},
        }


# 26 x 14 default layout: two banks of double-sided shelving with 1-wide aisles,
# cross aisles above, between and below the banks, a few pillars, 4 pack
# stations along the bottom and 8 robot parking spots along the top.
#
# 1-wide aisles with two-way traffic gridlock quickly (see DECISIONS.md), so the
# shelving zone uses one-way lanes: vertical aisles alternate direction, the
# top cross aisle flows west and the middle/bottom ones flow east. The pack
# zone is a loop (row 11 west, row 12 east, past the stations). Only the open
# area on the right is two-way.
DEFAULT_LAYOUT = [
    "##########################",
    "#H.H.H.H.H.H.H.H.........#",
    "#........................#",
    "#.SS.SS.SS.SS.SS.SS..X...#",
    "#.SS.SS.SS.SS.SS.SS......#",
    "#.SS.SS.SS.SS.SS.SS......#",
    "#........................#",
    "#.SS.SS.SS.SS.SS.SS...X..#",
    "#.SS.SS.SS.SS.SS.SS......#",
    "#.SS.SS.SS.SS.SS.SS......#",
    "#......................X.#",
    "#........................#",
    "#..P.....P.....P.....P...#",
    "##########################",
]


DEFAULT_LANES = [
    "..........................",
    "..........................",
    ".<<<<<<<<<<<<<<<<<<<......",
    ".v..^..v..^..v..^..v......",
    ".v..^..v..^..v..^..v......",
    ".v..^..v..^..v..^..v......",
    ".>>>>>>>>>>>>>>>>>>>......",
    ".v..^..v..^..v..^..v......",
    ".v..^..v..^..v..^..v......",
    ".v..^..v..^..v..^..v......",
    ".>>>>>>>>>>>>>>>>>>>......",
    ".<<<<<<<<<<<<<<<<<<<......",
    ".>>>>>>>>>>>>>>>>>>>......",
    "..........................",
]


def default_warehouse(one_way: bool = True) -> Warehouse:
    return Warehouse.from_ascii(DEFAULT_LAYOUT, DEFAULT_LANES if one_way else None)
