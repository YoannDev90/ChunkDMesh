import json5
import random
import os
import math

class ChunkyShape:
    """
    https://github.com/pop4959/Chunky/wiki/Shapes
    """
    SQUARE = "square"
    CIRCLE = "circle"
    TRIANGLE = "triangle"
    DIAMOND = "diamond"
    PENTAGON = "pentagon"
    HEXAGON = "hexagon"
    STAR = "star"


class ChunkyPattern:
    """
    https://github.com/pop4959/Chunky/wiki/Patterns
    """
    REGIONS = "regions"
    CONCENTRIC = "concentric"
    LOOP = "loop"
    SPIRAL = "spiral"

class ChunkyDimension:
    OVERWORLD = "overworld"
    NETHER = "nether"
    END = "end"
    CUSTOM = "custom"

class Config:
    def __init__(self, path="data/world_config.json5"):
        self.path = path
        self.config = load_config(path)
        self.world_name : str = self.config.get("world_name") or None
        self.dimension : str = self.config.get("dimension") or "overworld"
        self.center : list = self.config.get("center") or [float("nan"), float("nan")]
        self.seed : float = self.config.get("seed") or float("nan")
        self.radius : int = self.config.get("radius") or 1024
        self.shape : str = self.config.get("shape") or "square"
        self.pattern : str = self.config.get("pattern") or "regions"
        self.max_clients : int = self.config.get("max_clients") or None
        self.chunk_format : str = self.config.get("chunk_format") or "sha256"
        self.verification : bool = self.config.get("verification") or False
        self.use_spawn_as_center : bool = False

        if math.isnan(self.center[0]) or math.isnan(self.center[1]):
            self.center = [0, 0]
            self.use_spawn_as_center = True
        if self.radius <= 0:
            raise ValueError("Radius must be a positive integer")
        if math.isnan(self.seed):
            self.seed = random.randint(-10**18, 10**18)
        if self.shape not in [s for s in vars(ChunkyShape).values() if isinstance(s, str)]:
            raise ValueError(f"Invalid shape: {self.shape}")
        if self.pattern not in [s for s in vars(ChunkyPattern).values() if isinstance(s, str)]:
            raise ValueError(f"Invalid pattern: {self.pattern}")
        if math.isnan(self.max_clients) or self.max_clients > 100:
            self.max_clients = 100

    def __dict__(self):
        return {
            "world_name": self.world_name,
            "dimension": self.dimension,
            "center": self.center,
            "seed": self.seed,
            "radius": self.radius,
            "shape": self.shape,
            "pattern": self.pattern,
            "max_clients": self.max_clients,
            "chunk_format": self.chunk_format,
            "verification": self.verification,
            "use_spawn_as_center": self.use_spawn_as_center,
        }

def load_config(path="data/world_config.json5"):
    with open(path, "r") as f:
        config = json5.load(f)
    return config

if __name__ == "__main__":
    config = Config()
    print(config.__dict__())
