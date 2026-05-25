"""Implementation of Chunky patterns and related utilities.
https://github.com/pop4959/Chunky/wiki/Patterns
"""

from typing import Enum

class PatternType(Enum):
    REGIONS = "regions"
    CONCENTRIC = "concentric"
    LOOP = "loop"
    SPIRAL = "spiral"