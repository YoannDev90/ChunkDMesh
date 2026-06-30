"""Tests for tile cache LRU eviction."""


from map_generator.tile_cache import TileCache


class TestTileCache:
    def test_lru_eviction(self, tmp_path):
        cache = TileCache(tmp_path, max_mem_size=3)
        cache.set_tile_png(0, 0, b"png0", zoom=5)
        cache.set_tile_png(1, 0, b"png1", zoom=5)
        cache.set_tile_png(2, 0, b"png2", zoom=5)
        cache.set_tile_png(3, 0, b"png3", zoom=5)
        assert len(cache._mem_cache) == 3
        key = "tile:5:0:0"
        assert key not in cache._mem_cache

    def test_access_refreshes_lru(self, tmp_path):
        cache = TileCache(tmp_path, max_mem_size=3)
        cache.set_tile_png(0, 0, b"a", zoom=5)
        cache.set_tile_png(1, 0, b"b", zoom=5)
        cache.set_tile_png(2, 0, b"c", zoom=5)
        _ = cache.get_tile_png(0, 0, zoom=5)
        cache.set_tile_png(3, 0, b"d", zoom=5)
        assert cache.get_tile_png(0, 0, zoom=5) == b"a"

    def test_disk_persistence(self, tmp_path):
        cache = TileCache(tmp_path, max_mem_size=1)
        cache.set_tile_png(5, 5, b"hello", zoom=5)
        cache2 = TileCache(tmp_path, max_mem_size=100)
        assert cache2.get_tile_png(5, 5, zoom=5) == b"hello"

    def test_hover_data(self, tmp_path):
        cache = TileCache(tmp_path, max_mem_size=10)
        data = {"block": "stone", "biome": "plains"}
        cache.set_hover_data(10, 20, data)
        assert cache.get_hover_data(10, 20) == data
