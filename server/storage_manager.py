import hashlib
import logging
import shutil
from pathlib import Path

import zstd

logger = logging.getLogger(__name__)

STORAGE_DIR = Path(__file__).resolve().parent.parent / "data" / "storage"


class ChunkStorage:
    """Storage layer with transparent dedup + cleanup."""

    def __init__(self, storage_dir: Path = STORAGE_DIR):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    # ── Batch dir management ─────────────────────────────────────────────

    def batch_dir(self, batch_id: int) -> Path:
        return self.storage_dir / str(batch_id)

    def ensure_batch_dir(self, batch_id: int) -> Path:
        d = self.batch_dir(batch_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── Write ────────────────────────────────────────────────────────────

    def _blob_path(self, sha256: str) -> Path:
        blob_dir = self.storage_dir / ".blobs"
        blob_dir.mkdir(parents=True, exist_ok=True)
        return blob_dir / sha256

    def write_mca(self, batch_id: int, filename: str, data: bytes) -> tuple[str, int]:
        """Dedup: store by SHA-256, hardlink to batch dir. Returns (sha256, raw_size)."""
        sha256 = hashlib.sha256(data).hexdigest()
        raw_size = len(data)

        blob_path = self._blob_path(sha256)
        if not blob_path.exists():
            blob_path.write_bytes(data)

        # Hardlink from batch dir to blob store
        bdir = self.ensure_batch_dir(batch_id)
        dest = bdir / filename
        if not dest.exists():
            try:
                dest.hardlink_to(blob_path)
            except OSError:
                # Cross-device or no hardlink support: copy
                shutil.copy2(blob_path, dest)

        return sha256, raw_size

    def write_mca_from_path(self, batch_id: int, mca_path: Path) -> tuple[str, str, int]:
        """Convenience: read file, dedup store. Returns (filename, sha256, raw_size)."""
        data = mca_path.read_bytes()
        sha256, raw_size = self.write_mca(batch_id, mca_path.name, data)
        return mca_path.name, sha256, raw_size

    # ── Read ─────────────────────────────────────────────────────────────

    def read_mca(self, batch_id: int, filename: str) -> bytes | None:
        """Read .mca from batch dir (may be hardlink to blob)."""
        path = self.batch_dir(batch_id) / filename
        if path.exists():
            return path.read_bytes()
        return None

    def get_mca_path(self, batch_id: int, filename: str) -> Path | None:
        path = self.batch_dir(batch_id) / filename
        return path if path.exists() else None

    def get_mca_hash(self, batch_id: int, filename: str) -> str | None:
        path = self.batch_dir(batch_id) / filename
        if not path.exists():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()

    # ── Batch listing ────────────────────────────────────────────────────

    def list_batches(self) -> list[int]:
        return sorted(
            int(d.name) for d in self.storage_dir.iterdir()
            if d.is_dir() and d.name.isdigit()
        )

    def list_mca_files(self, batch_id: int) -> list[str]:
        bdir = self.batch_dir(batch_id)
        if not bdir.exists():
            return []
        return sorted(f.name for f in bdir.iterdir() if f.suffix == ".mca")

    # ── Cleanup ──────────────────────────────────────────────────────────

    def delete_batch(self, batch_id: int) -> bool:
        bdir = self.batch_dir(batch_id)
        if bdir.exists():
            shutil.rmtree(bdir)
            logger.info("Deleted batch %d storage", batch_id)
            return True
        return False

    def cleanup_after_assembly(self, keep_batch_ids: set[int] | None = None) -> dict:
        """Remove batch dirs after assembly, optionally keep specified ones."""
        keep = keep_batch_ids or set()
        removed = 0
        freed_bytes = 0
        for bid in self.list_batches():
            if bid in keep:
                continue
            bdir = self.batch_dir(bid)
            freed_bytes += sum(f.stat().st_size for f in bdir.rglob("*") if f.is_file())
            shutil.rmtree(bdir)
            removed += 1
        logger.info("Cleaned %d batches, freed %.1f MB", removed, freed_bytes / (1024 * 1024))
        return {"removed": removed, "freed_mb": round(freed_bytes / (1024 * 1024), 1)}

    def compact_blobs(self) -> dict:
        """Remove blob store entries not referenced by any batch dir."""
        blob_dir = self.storage_dir / ".blobs"
        if not blob_dir.exists():
            return {"removed": 0, "freed_mb": 0.0}

        # Collect all referenced hashes
        referenced: set[str] = set()
        for bid in self.list_batches():
            for f in self.batch_dir(bid).iterdir():
                if f.is_file() and not f.name.startswith("."):
                    try:
                        stats = f.stat()
                        if stats.st_nlink > 1 or True:
                            referenced.add(hashlib.sha256(f.read_bytes()).hexdigest())
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

    def total_size_mb(self) -> float:
        blob_dir = self.storage_dir / ".blobs"
        if blob_dir.exists():
            # Accurate: blob store represents actual disk usage (hardlinks share inodes)
            total = sum(f.stat().st_size for f in blob_dir.iterdir() if f.is_file())
        else:
            # Legacy: sum all batch files (may overcount hardlinks)
            seen_inodes: set[tuple[int, int]] = set()
            total = 0
            for bid in self.list_batches():
                for f in self.batch_dir(bid).rglob("*"):
                    if f.is_file():
                        ino = (f.stat().st_dev, f.stat().st_ino)
                        if ino not in seen_inodes:
                            seen_inodes.add(ino)
                            total += f.stat().st_size
        return round(total / (1024 * 1024), 1)
