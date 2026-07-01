import contextlib
import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class RustTiler:
    """Bridge to Rust mcmap binary.

    Batches renders per region: first request for any chunk in a region
    triggers rendering of ALL chunks in that region file (~9s for 1024).
    Subsequent chunks from the same region read from cache instantly.
    """

    def __init__(
        self, binary_path: str, palette_path: str = "", biome_colors_path: str = "", biome_tints_path: str = ""
    ):
        """Initialize Rust tiler bridge with paths to binary and palette files."""
        self.binary = binary_path
        self.palette_path = palette_path
        self.biome_colors_path = biome_colors_path
        self.biome_tints_path = biome_tints_path

    def _build_base_cmd(self) -> list[str]:
        cmd = [self.binary]
        for flag, path in [
            ("--palette", self.palette_path),
            ("--biome-colors", self.biome_colors_path),
            ("--biome-tints", self.biome_tints_path),
        ]:
            if path and Path(path).exists():
                cmd.extend([flag, path])
        return cmd

    def _render_region_all(self, region_path: str, output_dir: Path) -> bool:
        """Render all chunks in a region file to output_dir."""
        cmd = self._build_base_cmd()
        cmd.extend([region_path, "--all", "--output-dir", str(output_dir)])
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                stderr = result.stderr[:500] if result.stderr else ""
                logger.error("Region render failed exit=%d stderr=%s", result.returncode, stderr)
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.error("Region render timeout for %s", region_path)
            return False
        except Exception as e:
            logger.error("Region render error: %s", e)
            return False

    def render_chunk(self, region_path: str, chunk_x: int, chunk_z: int) -> tuple[bytes | None, dict | None]:
        """Render a single chunk via Rust binary. Returns (png_data, terrain_json)."""
        if not Path(self.binary).exists():
            logger.error("Rust binary not found: %s", self.binary)
            return None, None

        # Ensure region file exists
        if not Path(region_path).exists():
            logger.debug("Region not found: %s", region_path)
            return None, None

        # Use a persistent cache under the region path's directory
        region_path_obj = Path(region_path)
        region_stem = region_path_obj.stem  # r.0.0
        cache_dir = region_path_obj.parent / ".tile_cache" / region_stem
        cache_dir.mkdir(parents=True, exist_ok=True)

        png_path = cache_dir / f"chunk_{chunk_x}_{chunk_z}.png"
        marker = cache_dir / ".rendered"

        # Check if individual chunk is cached
        if png_path.exists():
            png_data = png_path.read_bytes()
            json_path = cache_dir / f"chunk_{chunk_x}_{chunk_z}.json"
            terrain = None
            if json_path.exists():
                with contextlib.suppress(Exception):
                    terrain = json.loads(json_path.read_text())
            return png_data, terrain

        # If region has not been fully rendered yet, render all chunks now
        if not marker.exists():
            logger.info("Rendering all chunks in %s...", region_stem)
            if not self._render_region_all(region_path, cache_dir):
                return None, None
            # Write marker
            marker.write_text("1")
            logger.info("Done rendering %s", region_stem)

        # After full render, try again
        if png_path.exists():
            png_data = png_path.read_bytes()
            return png_data, None

        return None, None
