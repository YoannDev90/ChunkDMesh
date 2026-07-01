import hashlib
import logging
import shutil
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

REGIONS_DIR = Path(__file__).resolve().parent.parent / "data" / "regions"


class ChunkStorage:
    """Flat region storage with content dedup.

    All .mca files land in data/regions/ — one flat dir, no per-batch nesting.
    Dedup via SHA-256 blobs in data/regions/.blobs/ + hardlinks.
    """

    _write_lock = threading.Lock()

    def __init__(self, regions_dir: Path = REGIONS_DIR):
        """Initialize storage with flat regions directory."""
        self.regions_dir = regions_dir
        self.regions_dir.mkdir(parents=True, exist_ok=True)

    def _blob_path(self, sha256: str) -> Path:
        d = self.regions_dir / ".blobs"
        d.mkdir(parents=True, exist_ok=True)
        return d / sha256

    def write_mca(self, filename: str, data: bytes) -> tuple[str, int]:
        """Store region file with dedup. Returns (sha256, raw_size)."""
        sha256 = hashlib.sha256(data).hexdigest()
        raw_size = len(data)

        with self._write_lock:
            blob = self._blob_path(sha256)
            if not blob.exists():
                tmp = blob.with_suffix(".tmp")
                tmp.write_bytes(data)
                try:
                    tmp.rename(blob)
                except FileExistsError:
                    tmp.unlink()

            dest = self.regions_dir / filename
            if not dest.exists():
                try:
                    dest.hardlink_to(blob)
                except OSError:
                    shutil.copy2(blob, dest)

        return sha256, raw_size

    def read_mca(self, filename: str) -> bytes | None:
        """Read region file bytes. Returns None if missing."""
        path = self.regions_dir / filename
        return path.read_bytes() if path.exists() else None

    def get_mca_path(self, filename: str) -> Path | None:
        """Return path to region file if it exists."""
        path = self.regions_dir / filename
        return path if path.exists() else None

    def get_mca_hash(self, filename: str) -> str | None:
        """Compute SHA-256 hash of a stored .mca file."""
        path = self.regions_dir / filename
        if not path.exists():
            return None
        from constants import compute_file_hash

        return compute_file_hash(path)

    def list_regions(self) -> list[str]:
        """List all stored .mca region filenames."""
        return sorted(f.name for f in self.regions_dir.iterdir() if f.suffix == ".mca")

    def total_size_mb(self) -> float:
        """Compute total storage size in MB (blobs or .mca files)."""
        blob_dir = self.regions_dir / ".blobs"
        if blob_dir.exists():
            total = sum(f.stat().st_size for f in blob_dir.iterdir() if f.is_file())
        else:
            total = sum(f.stat().st_size for f in self.regions_dir.iterdir() if f.is_file() and f.suffix == ".mca")
        return round(total / (1024 * 1024), 1)

    def compact_blobs(self) -> dict:
        """Remove unreferenced blobs."""
        blob_dir = self.regions_dir / ".blobs"
        if not blob_dir.exists():
            return {"removed": 0, "freed_mb": 0.0}

        referenced: set[str] = set()
        for f in self.regions_dir.iterdir():
            if f.is_file() and f.suffix == ".mca":
                try:
                    if f.stat().st_nlink > 1:
                        bname = f.resolve().name
                        if len(bname) == 64:
                            referenced.add(bname)
                except Exception:
                    pass

        removed = 0
        freed = 0
        for blob in blob_dir.iterdir():
            if blob.name not in referenced:
                freed += blob.stat().st_size
                blob.unlink()
                removed += 1

        logger.info("Compact blobs: removed %d, freed %.1f MB", removed, freed / (1024 * 1024))
        return {"removed": removed, "freed_mb": round(freed / (1024 * 1024), 1)}
