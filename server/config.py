import asyncio
import math
import random
from pathlib import Path
from typing import Optional

import json5
from mc_utils import (get_chunky_version, get_loader_version,
                      get_minecraft_versions)


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


class SupportedLoaders:
    FABRIC = "fabric"
    FORGE = "forge"
    QUILT = "quilt"
    NEOFORGE = "neoforge"


class Config:
    def __init__(self, path: str = None):
        if path is None:
            path = str(Path(__file__).resolve().parent.parent / "data" / "world_config.json5")
        self.path = path
        self.config = load_config(path)
        self._validated = False

        self.minecraft_version: str = self._clean_str(self.config.get("minecraft_version"))
        self.minecraft_loader: str = self._clean_str(self.config.get("minecraft_loader"))
        self.loader_version: str = self._clean_str(self.config.get("loader_version"))
        self.chunky_version: str = self._clean_str(self.config.get("chunky_version"))
        self.world_name: str = self.config.get("world_name")
        self.dimension: str = self.config.get("dimension") or "overworld"
        self.center: list = self.config.get("center") or [float("nan"), float("nan")]
        self.seed: float = self.config.get("seed") or float("nan")
        self.radius: int = self.config.get("radius") or 1024
        self.shape: str = self.config.get("shape") or "square"
        self.pattern: str = self.config.get("pattern") or "regions"
        self.max_clients: int = self.config.get("max_clients") or 100
        self.chunk_format: str = self.config.get("chunk_format") or "sha256"
        self.verification: bool = self.config.get("verification") or False
        self.use_spawn_as_center: bool = False

        self._normalize_defaults()

    @staticmethod
    def _clean_str(value) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        return str(value)

    def save_config(self) -> None:
        with open(self.path, "w") as f:
            json5.dump(self.to_dict(), f, indent=4)

    def _normalize_defaults(self) -> None:
        if (
            isinstance(self.center[0], (int, float))
            and isinstance(self.center[1], (int, float))
        ):
            if math.isnan(self.center[0]) or math.isnan(self.center[1]):
                self.center = [None, None]
                self.use_spawn_as_center = True

        if self.center[0] is None or self.center[1] is None:
            self.center = [None, None]
            self.use_spawn_as_center = True

        if self.radius <= 0:
            raise ValueError("Radius must be a positive integer")

        if math.isnan(self.seed):
            self.seed = random.randint(-(10**18), 10**18)

        valid_dimensions = [
            d for d in vars(ChunkyDimension).values() if isinstance(d, str)
        ]
        if self.dimension not in valid_dimensions:
            raise ValueError(f"Invalid dimension: {self.dimension}")

        valid_shapes = [s for s in vars(ChunkyShape).values() if isinstance(s, str)]
        if self.shape not in valid_shapes:
            raise ValueError(f"Invalid shape: {self.shape}")

        valid_patterns = [s for s in vars(ChunkyPattern).values() if isinstance(s, str)]
        if self.pattern not in valid_patterns:
            raise ValueError(f"Invalid pattern: {self.pattern}")

        if (
            self.max_clients is None
            or self.max_clients > 100
            or self.max_clients <= 0
            or not isinstance(self.max_clients, int)
        ):
            self.max_clients = 100

        self.save_config()

    async def validate(self) -> None:
        if self._validated:
            return

        supported_loaders = [
            l for l in vars(SupportedLoaders).values() if isinstance(l, str)
        ]
        if self.minecraft_loader not in supported_loaders:
            raise ValueError(f"Invalid Minecraft loader: {self.minecraft_loader}")

        minecraft_versions = await get_minecraft_versions()
        if self.minecraft_version not in minecraft_versions:
            raise ValueError(
                f"Invalid Minecraft version: {self.minecraft_version}. "
                f"Available: {minecraft_versions[:3]}..."
            )

        loader_versions = await get_loader_version(
            loader=self.minecraft_loader, minecraft_version=self.minecraft_version
        )
        if self.loader_version not in loader_versions:
            raise ValueError(
                f"Invalid loader version: {self.loader_version} for loader "
                f"{self.minecraft_loader} and Minecraft version {self.minecraft_version}"
            )

        chunky_id = await get_chunky_version(
            version=self.chunky_version,
            loader=self.minecraft_loader,
            minecraft_version=self.minecraft_version,
        )
        if not chunky_id:
            raise ValueError(
                f"Invalid Chunky version: {self.chunky_version} for loader "
                f"{self.minecraft_loader} and Minecraft version {self.minecraft_version}"
            )

        self.save_config()
        self._validated = True

    async def __aenter__(self):
        await self.validate()
        return self

    def to_dict(self) -> dict:
        mods_zip_path = Path(__file__).resolve().parent.parent / "data" / "mods.zip"
        return {
            "minecraft_version": self.minecraft_version,
            "minecraft_loader": self.minecraft_loader,
            "loader_version": self.loader_version,
            "chunky_version": self.chunky_version,
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
            "has_mods_zip": mods_zip_path.exists(),
        }


def load_config(path: str = "data/world_config.json5") -> dict:
    with open(path, "r") as f:
        config = json5.load(f)
    return config
