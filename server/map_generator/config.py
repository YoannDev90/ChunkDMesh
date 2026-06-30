from dataclasses import dataclass
from pathlib import Path


@dataclass
class MapConfig:
    region_dir: str
    tile_cache_dir: str
    rust_binary: str
    palette_path: str
    biome_colors_path: str
    biome_tints_path: str

    enable_shading: bool = True
    enable_biome_tint: bool = True
    enable_waterflow: bool = True

    light_direction: tuple = (-0.5, 0.7, 0.5)
    height_exaggeration: float = 2.0
    shadow_strength: float = 0.7
    cave_darkness: float = 0.6

    min_river_length: int = 4
    waterfall_threshold: float = 5.0

    redis_url: str = "redis://localhost:6379"
    cache_ttl_seconds: int = 3600
    hover_cache_ttl: int = 300

    tile_size: int = 256
    chunk_blocks: int = 16

    @classmethod
    def from_flat_regions_dir(cls, regions_dir: str) -> "MapConfig":
        base = Path(__file__).resolve().parent.parent.parent
        data_dir = base / "data"
        return cls(
            region_dir=regions_dir,
            tile_cache_dir=str(data_dir / ".map_cache"),
            rust_binary=str(base / "bin" / "rust_tiler" / "target" / "release" / "mcmap"),
            palette_path=str(data_dir / "block_colors.json"),
            biome_colors_path=str(data_dir / "biome_colors.json"),
            biome_tints_path=str(data_dir / "biome_tint_blocks.json"),
        )

    @property
    def region_path(self) -> Path:
        return Path(self.region_dir)

    @property
    def cache_path(self) -> Path:
        return Path(self.tile_cache_dir)
