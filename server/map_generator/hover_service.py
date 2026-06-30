import logging
from pathlib import Path

from .rust_bridge import RustTiler
from .tile_cache import TileCache

logger = logging.getLogger(__name__)

BIOME_REGISTRY: dict[int, str] = {
    0: "minecraft:ocean",
    1: "minecraft:plains",
    2: "minecraft:desert",
    3: "minecraft:windswept_hills",
    4: "minecraft:forest",
    5: "minecraft:taiga",
    6: "minecraft:swamp",
    7: "minecraft:river",
    8: "minecraft:nether_wastes",
    9: "minecraft:the_end",
    10: "minecraft:frozen_ocean",
    11: "minecraft:frozen_river",
    12: "minecraft:snowy_plains",
    13: "minecraft:snowy_beach",
    14: "minecraft:windswept_gravelly_hills",
    15: "minecraft:flower_forest",
    16: "minecraft:birch_forest",
    17: "minecraft:dark_forest",
    18: "minecraft:old_growth_pine_taiga",
    19: "minecraft:old_growth_spruce_taiga",
    20: "minecraft:snowy_taiga",
    21: "minecraft:savanna",
    22: "minecraft:savanna_plateau",
    23: "minecraft:badlands",
    24: "minecraft:wooded_badlands",
    25: "minecraft:jagged_peaks",
    26: "minecraft:stony_peaks",
    27: "minecraft:frozen_peaks",
    28: "minecraft:meadow",
    29: "minecraft:grove",
    30: "minecraft:snowy_slopes",
    31: "minecraft:cherry_grove",
    32: "minecraft:lush_caves",
    33: "minecraft:dripstone_caves",
    34: "minecraft:deep_dark",
    35: "minecraft:mangrove_swamp",
    36: "minecraft:deep_ocean",
    37: "minecraft:warm_ocean",
    38: "minecraft:lukewarm_ocean",
    39: "minecraft:cold_ocean",
    40: "minecraft:deep_warm_ocean",
    41: "minecraft:deep_lukewarm_ocean",
    42: "minecraft:deep_cold_ocean",
    43: "minecraft:deep_frozen_ocean",
    44: "minecraft:bamboo_jungle",
    45: "minecraft:sparse_jungle",
    46: "minecraft:windswept_forest",
    47: "minecraft:windswept_savanna",
    48: "minecraft:eroded_badlands",
    49: "minecraft:mushroom_fields",
    50: "minecraft:ice_spikes",
    51: "minecraft:sunflower_plains",
    52: "minecraft:snowy_slopes",
}

BLOCK_REGISTRY: dict[int, str] = {
    0: "minecraft:air",
    1: "minecraft:stone",
    2: "minecraft:grass_block",
    3: "minecraft:dirt",
    9: "minecraft:water",
}


class HoverService:
    def __init__(self, region_dir: str, tiler: RustTiler, cache: TileCache):
        self.region_dir = Path(region_dir)
        self.tiler = tiler
        self.cache = cache

    def _get_region_path(self, chunk_x: int, chunk_z: int) -> str | None:
        region_x = chunk_x >> 5
        region_z = chunk_z >> 5
        path = self.region_dir / f"r.{region_x}.{region_z}.mca"
        return str(path) if path.exists() else None

    def get_hover_data(self, chunk_x: int, chunk_z: int) -> dict:
        cached = self.cache.get_hover_data(chunk_x, chunk_z)
        if cached:
            return cached

        region_path = self._get_region_path(chunk_x, chunk_z)
        if not region_path:
            return {"error": "Region file not found", "chunk": {"x": chunk_x, "z": chunk_z}}

        _, terrain = self.tiler.render_chunk(region_path, chunk_x, chunk_z)
        if not terrain:
            return {"error": "Failed to render chunk", "chunk": {"x": chunk_x, "z": chunk_z}}

        result = {
            "chunk": {"x": chunk_x, "z": chunk_z},
            "terrain": terrain,
            "metadata": self._compute_metadata(terrain),
        }
        self.cache.set_hover_data(chunk_x, chunk_z, result)
        return result

    def get_block_at_pixel(self, chunk_x: int, chunk_z: int, local_x: int, local_z: int) -> dict:
        if not (0 <= local_x < 16 and 0 <= local_z < 16):
            return {"error": "Invalid local coords"}

        hover = self.get_hover_data(chunk_x, chunk_z)
        if "error" in hover:
            return hover

        terrain = hover["terrain"]
        try:
            block_id = terrain["block_ids"][local_z][local_x]
            biome_name = terrain["biomes"][local_z][local_x]
            height = terrain["heights"][local_z][local_x]
            block_name = terrain["block_names"][local_z][local_x]
        except (IndexError, KeyError) as e:
            return {"error": f"Missing terrain data: {e}"}

        return {
            "block": {
                "id": block_id,
                "name": block_name or BLOCK_REGISTRY.get(block_id, "minecraft:unknown"),
                "height": int(height),
            },
            "biome": {
                "id": -1,
                "name": biome_name or "minecraft:unknown",
            },
            "coords": {
                "chunk_x": chunk_x,
                "chunk_z": chunk_z,
                "local_x": local_x,
                "local_z": local_z,
                "world_x": chunk_x * 16 + local_x,
                "world_z": chunk_z * 16 + local_z,
                "y": int(height),
            },
        }

    @staticmethod
    def _compute_metadata(terrain: dict) -> dict:
        _heights = terrain.get("heights", [])
        caves = terrain.get("has_caves", [])
        water = terrain.get("water_map", [])
        return {
            "water_present": any(any(row) for row in water),
            "cave_present": any(any(row) for row in caves),
            "min_height": terrain.get("min_height", 0),
            "max_height": terrain.get("max_height", 0),
        }
