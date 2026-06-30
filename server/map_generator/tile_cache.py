import json
import logging
from collections import OrderedDict
from pathlib import Path

from constants import TILE_CACHE_MAX_SIZE

logger = logging.getLogger(__name__)


class TileCache:
    def __init__(self, disk_path: Path, max_mem_size: int = TILE_CACHE_MAX_SIZE):
        self.disk_path = disk_path
        self.disk_path.mkdir(parents=True, exist_ok=True)
        self._mem_cache: OrderedDict[str, bytes | dict] = OrderedDict()
        self._max_mem_size = max_mem_size

    def _evict(self):
        while len(self._mem_cache) > self._max_mem_size:
            self._mem_cache.popitem(last=False)

    def _tile_key(self, chunk_x: int, chunk_z: int, zoom: int = 5) -> str:
        return f"z{zoom}_x{chunk_x}_z{chunk_z}"

    def _tile_path(self, chunk_x: int, chunk_z: int, zoom: int = 5) -> Path:
        return self.disk_path / f"{self._tile_key(chunk_x, chunk_z, zoom)}.png"

    def get_tile_png(
        self, chunk_x: int, chunk_z: int, zoom: int = 5
    ) -> bytes | None:
        key = f"tile:{zoom}:{chunk_x}:{chunk_z}"
        if key in self._mem_cache:
            cached = self._mem_cache[key]
            self._mem_cache.move_to_end(key)
            if isinstance(cached, bytes):
                return cached

        path = self._tile_path(chunk_x, chunk_z, zoom)
        if path.exists():
            data = path.read_bytes()
            self._mem_cache[key] = data
            self._evict()
            return data
        return None

    def set_tile_png(
        self, chunk_x: int, chunk_z: int, png_data: bytes, zoom: int = 5
    ):
        key = f"tile:{zoom}:{chunk_x}:{chunk_z}"
        path = self._tile_path(chunk_x, chunk_z, zoom)
        path.write_bytes(png_data)
        self._mem_cache[key] = png_data
        self._evict()

    def _hover_path(self, chunk_x: int, chunk_z: int) -> Path:
        return self.disk_path / f"hover_{chunk_x}_{chunk_z}.json"

    def get_hover_data(self, chunk_x: int, chunk_z: int) -> dict | None:
        key = f"hover:{chunk_x}:{chunk_z}"
        if key in self._mem_cache:
            cached = self._mem_cache[key]
            self._mem_cache.move_to_end(key)
            if isinstance(cached, dict):
                return cached

        path = self._hover_path(chunk_x, chunk_z)
        if path.exists():
            try:
                data = json.loads(path.read_text())
                self._mem_cache[key] = data
                self._evict()
                return data
            except Exception as e:
                logger.warning("Failed to read hover cache %s: %s", path, e)
        return None

    def set_hover_data(self, chunk_x: int, chunk_z: int, data: dict):
        key = f"hover:{chunk_x}:{chunk_z}"
        path = self._hover_path(chunk_x, chunk_z)
        try:
            path.write_text(json.dumps(data))
            self._mem_cache[key] = data
            self._evict()
        except Exception as e:
            logger.warning("Failed to write hover cache %s: %s", path, e)

    def invalidate_tile(self, chunk_x: int, chunk_z: int, zoom: int = 5):
        key = f"tile:{zoom}:{chunk_x}:{chunk_z}"
        self._mem_cache.pop(key, None)
        path = self._tile_path(chunk_x, chunk_z, zoom)
        path.unlink(missing_ok=True)

        hover_key = f"hover:{chunk_x}:{chunk_z}"
        self._mem_cache.pop(hover_key, None)
        hover_path = self._hover_path(chunk_x, chunk_z)
        hover_path.unlink(missing_ok=True)
