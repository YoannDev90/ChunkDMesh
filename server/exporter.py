from __future__ import annotations

import logging
import tarfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

EXPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"


class ExportManager:
    def __init__(self, world_name: str, exports_dir: Path = EXPORTS_DIR):
        self.world_name = world_name
        self.exports_dir = exports_dir
        self.world_dir = exports_dir / world_name

    def export(self) -> Path:
        if not self.world_dir.exists():
            raise FileNotFoundError(f"World directory not found: {self.world_dir}")

        region_dir = self.world_dir / "world" / "region"
        if not region_dir.exists() or not list(region_dir.glob("*.mca")):
            raise FileNotFoundError("No .mca files found in world/region/")

        timestamp = int(time.time())
        archive_name = f"{self.world_name}_{timestamp}.tar.gz"
        archive_path = self.exports_dir / archive_name

        logger.info("Creating archive: %s", archive_path)

        with tarfile.open(archive_path, "w:gz") as tar:
            for mca_file in sorted(region_dir.glob("*.mca")):
                arcname = f"{self.world_name}/world/region/{mca_file.name}"
                tar.add(mca_file, arcname=arcname)

        size_mb = archive_path.stat().st_size / (1024 * 1024)
        logger.info("Archive created: %s (%.2f MB)", archive_path, size_mb)

        return archive_path

    def list_archives(self) -> list[dict]:
        archives = []
        for f in self.exports_dir.glob(f"{self.world_name}_*.tar.gz"):
            archives.append(
                {
                    "name": f.name,
                    "path": str(f),
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                }
            )
        return sorted(archives, key=lambda x: x["name"], reverse=True)

    def get_latest_archive(self) -> Path | None:
        archives = self.list_archives()
        if archives:
            return Path(archives[0]["path"])
        return None

    def delete_archive(self, archive_name: str) -> bool:
        archive_path = self.exports_dir / archive_name
        if archive_path.exists() and archive_path.parent == self.exports_dir:
            archive_path.unlink()
            logger.info("Deleted archive: %s", archive_path)
            return True
        return False
