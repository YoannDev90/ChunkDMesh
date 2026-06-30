import logging
from pathlib import Path

from storage_manager import REGIONS_DIR

logger = logging.getLogger(__name__)

EXPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"


class RegionAssembler:
    """Assemble region files from flat storage into export dir.

    Since we now store directly in data/regions/, assembly is just
    a copy/link to the export directory for .tar.gz packaging.
    """

    def __init__(self, world_name: str, exports_dir: Path = EXPORTS_DIR):
        self.world_name = world_name
        self.exports_dir = exports_dir
        self.world_dir = exports_dir / world_name
        self.region_dir = self.world_dir / "world" / "region"

    async def assemble(self) -> dict:
        """Copy all validated region files from flat storage to export dir."""
        self.region_dir.mkdir(parents=True, exist_ok=True)

        regions = REGIONS_DIR
        if not regions.exists():
            return {"assembled": 0, "total": 0, "errors": []}

        errors: list[str] = []
        assembled = 0
        total = 0

        for f in sorted(regions.iterdir()):
            if f.suffix != ".mca":
                continue
            total += 1
            dest = self.region_dir / f.name
            if dest.exists():
                continue
            try:
                dest.hardlink_to(f)
            except OSError:
                try:
                    import shutil
                    shutil.copy2(f, dest)
                except Exception as e:
                    errors.append(f"{f.name}: {e}")
                    continue
            assembled += 1

        logger.info("Assembled %d/%d regions to %s", assembled, total, self.region_dir)
        return {"assembled": assembled, "total": total, "errors": errors[:10]}

    def get_progress(self) -> dict:
        if not self.region_dir.exists():
            return {"total_files": 0, "total_size_mb": 0.0}
        files = list(self.region_dir.glob("*.mca"))
        size_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
        return {"total_files": len(files), "total_size_mb": round(size_mb, 1)}
