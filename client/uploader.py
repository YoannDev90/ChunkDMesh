import hashlib
import json
import struct
from pathlib import Path

import httpx
import zstd

_BATCH_SIZE = 50


class RegionUploader:
    """Handles .mca file upload, hashing, and tile upload to server."""

    def __init__(self, server_url: str, token: str):
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}

    def collect_mca_files(self, region_dir: Path) -> list[Path]:
        """List .mca files in region directory.

        Args:
            region_dir: Path to region directory.

        Returns: Sorted list of .mca file paths.
        """
        return sorted(region_dir.glob("*.mca"))

    def compute_hashes(self, mca_files: list[Path]) -> dict[str, str]:
        """Compute SHA-256 hashes for .mca files.

        Args:
            mca_files: List of .mca file paths.

        Returns: Dict mapping filename to hex digest.
        """
        hashes = {}
        for f in mca_files:
            sha256 = hashlib.sha256()
            with open(f, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 64), b""):
                    sha256.update(chunk)
            hashes[f.name] = sha256.hexdigest()
        return hashes

    def compress_zstd(self, data: bytes, level: int = 3) -> bytes:
        """Compress data using Zstandard.

        Args:
            data: Raw bytes to compress.
            level: Compression level.

        Returns: Compressed bytes.
        """
        return zstd.compress(data, level)

    def upload_file(self, batch_id: int, mca_path: Path) -> dict:
        """Upload compressed .mca file to server.

        Args:
            batch_id: Batch ID.
            mca_path: Path to .mca file.

        Returns: Server response dict.
        """
        raw = mca_path.read_bytes()
        compressed = self.compress_zstd(raw)

        with httpx.Client(follow_redirects=True, timeout=120) as client:
            resp = client.put(
                f"{self.server_url}/tasks/upload/{batch_id}",
                content=compressed,
                headers={
                    **self.headers,
                    "Content-Type": "application/octet-stream",
                    "X-Filename": mca_path.name,
                },
            )
            resp.raise_for_status()
            return resp.json()

    def submit_hashes(self, batch_id: int, chunk_hashes: dict[str, str]) -> dict:
        """Submit file hashes to server for batch completion.

        Args:
            batch_id: Batch ID.
            chunk_hashes: Dict mapping filename to SHA-256 hash.

        Returns: Server response dict.
        """
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            resp = client.post(
                f"{self.server_url}/tasks/submit",
                json={"batch_id": batch_id, "chunk_hashes": chunk_hashes},
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _make_binary_payload(tiles: list[tuple[int, int, bytes]]) -> bytes:
        """Pack tiles into binary format: (chunk_x:i32, chunk_z:i32, size:u32, png_data)..."""
        buf = bytearray()
        for cx, cz, png in tiles:
            buf.extend(struct.pack("<iiI", cx, cz, len(png)))
            buf.extend(png)
        return bytes(buf)

    def _upload_batch(self, tiles: list[tuple[int, int, bytes]]) -> dict:
        """Send a batch of tiles to the server."""
        payload = self._make_binary_payload(tiles)
        compressed = self.compress_zstd(payload)

        with httpx.Client(follow_redirects=True, timeout=120) as client:
            resp = client.put(
                f"{self.server_url}/tiles/upload/batch",
                content=compressed,
                headers={**self.headers, "Content-Type": "application/octet-stream"},
            )
            resp.raise_for_status()
            return resp.json()

    def upload_tiles_batch(self, tile_paths: dict[str, Path], output_dir: Path) -> dict:
        """Upload multiple PNG tiles in batches of 50."""
        uploaded = 0
        errors = []
        pending: list[tuple[int, int, bytes]] = []

        for stem, png_path in tile_paths.items():
            parts = stem.split("_")
            if len(parts) != 3:
                continue
            try:
                chunk_x = int(parts[1])
                chunk_z = int(parts[2])
            except ValueError:
                continue

            png_data = png_path.read_bytes()
            pending.append((chunk_x, chunk_z, png_data))

            if len(pending) >= _BATCH_SIZE:
                try:
                    result = self._upload_batch(pending)
                    uploaded += result.get("count", len(pending))
                except Exception as e:
                    errors.append(f"batch of {len(pending)}: {e}")
                pending.clear()

        # Upload remaining tiles
        if pending:
            try:
                result = self._upload_batch(pending)
                uploaded += result.get("count", len(pending))
            except Exception as e:
                errors.append(f"final batch of {len(pending)}: {e}")

        return {"uploaded": uploaded, "errors": errors}

    def upload_hover_data(self, chunk_x: int, chunk_z: int, terrain: dict) -> dict:
        """Upload hover/terrain JSON data for a chunk."""
        payload = json.dumps(terrain)

        with httpx.Client(follow_redirects=True, timeout=10) as client:
            resp = client.put(
                f"{self.server_url}/tiles/hover/{chunk_x}/{chunk_z}",
                content=payload,
                headers={
                    **self.headers,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()

    def upload_batch(
        self,
        batch_id: int,
        region_dir: Path,
        region_coords: list[tuple[int, int]],
    ) -> dict:
        """Upload all .mca files in region and submit hashes.

        Args:
            batch_id: Batch ID.
            region_dir: Region directory path.
            region_coords: List of (rx, rz) region coordinates.

        Returns: Dict with upload results.

        Raises: FileNotFoundError if no .mca files found.
        """
        mca_files = self.collect_mca_files(region_dir)

        if not mca_files:
            raise FileNotFoundError(f"No .mca files found in {region_dir}")

        print(f"Found {len(mca_files)} .mca files")

        hashes = self.compute_hashes(mca_files)
        print(f"Computed hashes for {len(hashes)} files")

        for mca in mca_files:
            name = mca.name
            print(f"Uploading {name} ({mca.stat().st_size} bytes)...")
            result = self.upload_file(batch_id, mca)
            print(f"  -> {result}")

        print("Submitting hashes...")
        submit_result = self.submit_hashes(batch_id, hashes)
        print(f"Submit result: {submit_result}")

        return {
            "batch_id": batch_id,
            "files_uploaded": len(mca_files),
            "hashes": hashes,
            "submit_result": submit_result,
        }
