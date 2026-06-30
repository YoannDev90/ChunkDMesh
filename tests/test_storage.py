"""Tests for storage manager dedup and thread safety."""


from storage_manager import ChunkStorage


class TestChunkStorage:
    def test_write_and_read(self, tmp_path):
        storage = ChunkStorage(tmp_path)
        sha, size = storage.write_mca("r.0.0.mca", b"test data")
        assert len(sha) == 64
        assert size == 9
        data = storage.read_mca("r.0.0.mca")
        assert data == b"test data"

    def test_dedup_creates_hardlink(self, tmp_path):
        storage = ChunkStorage(tmp_path)
        storage.write_mca("r.0.0.mca", b"dedup test")
        storage.write_mca("r.1.1.mca", b"dedup test")
        p1 = tmp_path / "r.0.0.mca"
        p2 = tmp_path / "r.1.1.mca"
        assert p1.stat().st_nlink >= 2
        assert p2.stat().st_nlink >= 2

    def test_read_nonexistent(self, tmp_path):
        storage = ChunkStorage(tmp_path)
        assert storage.read_mca("nope.mca") is None

    def test_list_regions(self, tmp_path):
        storage = ChunkStorage(tmp_path)
        storage.write_mca("r.0.0.mca", b"data1")
        storage.write_mca("r.1.0.mca", b"data2")
        regions = storage.list_regions()
        assert "r.0.0.mca" in regions
        assert "r.1.0.mca" in regions
