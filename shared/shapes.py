"""Implementation of Chunky shapes and related utilities.
https://github.com/pop4959/Chunky/wiki/Shapes
"""

from enum import Enum


class ShapeType(Enum):
    SQUARE = "square"
    CIRCLE = "circle"
    TRIANGLE = "triangle"
    DIAMOND = "diamond"
    PENTAGON = "pentagon"
    HEXAGON = "hexagon"
    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"


class SquareShape:
    def __init__(self, size: int):
        self.radius = size


class CircleShape:
    def __init__(self, radius: int):
        self.radius = radius


class TriangleShape:
    def __init__(self, size: int):
        self.radius = size


class DiamondShape:
    def __init__(self, size: int):
        self.radius = size


class PentagonShape:
    def __init__(self, size: int):
        self.radius = size


class HexagonShape:
    def __init__(self, size: int):
        self.radius = size


class RectangleShape:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height


class EllipseShape:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
