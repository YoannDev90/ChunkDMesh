import logging
import shutil
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from db import Batch, get_db_session

logger = logging.getLogger(__name__)

EXPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"


class RegionAssembler:
    def __init__(self, world_name: str, exports_dir: Path = EXPORTS_DIR):
        self.world_name = world_name
        self.exports_dir = exports_dir
        self.world_dir = exports_dir / world_name
        self.region_dir = self.world_dir / "world" / "region"
        self.storage_dir = Path(__file__).resolve().parent.parent / "data" / "storage"

    async def assemble(self) -> dict:
        self.region_dir.mkdir(parents=True, exist_ok=True)

        async with get_db_session() as session:
            result = await session.execute(
                select(Batch).where(Batch.status == "validated")
            )
            validated_batches = result.scalars().all()

        if not validated_batches:
            logger.info("No validated batches to assemble")
            return {"assembled": 0, "skipped": 0}

        assembled = 0
        skipped = 0
        seen_regions: dict[str, int] = {}

        for batch in validated_batches:
            batch_dir = self.storage_dir / str(batch.id)
            if not batch_dir.exists():
                logger.warning("Storage dir missing for batch %d", batch.id)
                skipped += 1
                continue

            for mca_file in batch_dir.glob("*.mca"):
                dest = self.region_dir / mca_file.name

                if mca_file.name in seen_regions:
                    logger.debug(
                        "Region %s already assembled, skipping (batch %d)",
                        mca_file.name,
                        batch.id,
                    )
                    skipped += 1
                    continue

                shutil.copy2(mca_file, dest)
                seen_regions[mca_file.name] = batch.id
                assembled += 1
                logger.info(
                    "Copied %s from batch %d", mca_file.name, batch.id
                )

        return {
            "assembled": assembled,
            "skipped": skipped,
            "total_batches": len(validated_batches),
        }

    def get_progress(self) -> dict:
        if not self.region_dir.exists():
            return {"total_files": 0, "total_size_mb": 0}

        files = list(self.region_dir.glob("*.mca"))
        total_size = sum(f.stat().st_size for f in files)

        return {
            "total_files": len(files),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }

    def get_region_path(self, region_x: int, region_z: int) -> Path:
        return self.region_dir / f"r.{region_x}.{region_z}.mca"

    async def is_complete(self, expected_regions: int) -> bool:
        if not self.region_dir.exists():
            return False
        current = len(list(self.region_dir.glob("*.mca")))
        return current >= expected_regions

    def cleanup_storage(self):
        if self.storage_dir.exists():
            shutil.rmtree(self.storage_dir)
            logger.info("Cleaned up storage directory")
