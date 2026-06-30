"""Geometry helpers for task generation."""

from __future__ import annotations

import math
from collections.abc import Iterator

from config import ChunkyShape


def generate_spiral_order(radius_regions: int) -> Iterator[tuple[int, int]]:
    """Generate region coordinates in concentric rings from center (0,0).

    Yields (rx, rz) tuples ordered by distance from center.
    """
    yield (0, 0)

    for ring in range(1, radius_regions + 1):
        coords: list[tuple[int, int]] = []

        for x in range(-ring, ring + 1):
            coords.append((x, -ring))
        for z in range(-ring + 1, ring + 1):
            coords.append((ring, z))
        for x in range(ring - 1, -ring - 1, -1):
            coords.append((x, ring))
        for z in range(ring - 1, -ring, -1):
            coords.append((-ring, z))

        coords.sort(key=lambda c: (c[0] ** 2 + c[1] ** 2, math.atan2(c[1], c[0])))
        yield from coords


def is_inside_shape(cx: int, cz: int, shape: str, radius_chunks: int) -> bool:
    """Check if a chunk coordinate (cx, cz) is inside the given shape with radius."""
    if shape == ChunkyShape.SQUARE:
        return True
    if shape == ChunkyShape.CIRCLE:
        return (cx**2 + cz**2) <= radius_chunks**2
    if shape in (ChunkyShape.DIAMOND, ChunkyShape.TRIANGLE):
        return abs(cx) + abs(cz) <= radius_chunks
    if shape in (ChunkyShape.HEXAGON, ChunkyShape.PENTAGON, ChunkyShape.STAR):
        return (cx**2 + cz**2) <= radius_chunks**2
    return True
