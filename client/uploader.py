import hashlib
from pathlib import Path

import httpx
import zstd


class RegionUploader:
    def __init__(self, server_url: str, token: str):
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}

    def collect_mca_files(self, region_dir: Path) -> list[Path]:
        return sorted(region_dir.glob("*.mca"))

    def compute_hashes(self, mca_files: list[Path]) -> dict[str, str]:
        hashes = {}
        for f in mca_files:
            sha256 = hashlib.sha256()
            with open(f, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 64), b""):
                    sha256.update(chunk)
            hashes[f.name] = sha256.hexdigest()
        return hashes

    def compress_zstd(self, data: bytes, level: int = 3) -> bytes:
        return zstd.compress(data, level)

    def upload_file(self, batch_id: int, mca_path: Path) -> dict:
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
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            resp = client.post(
                f"{self.server_url}/tasks/submit",
                json={"batch_id": batch_id, "chunk_hashes": chunk_hashes},
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    def upload_batch(
        self,
        batch_id: int,
        region_dir: Path,
        region_coords: list[tuple[int, int]],
    ) -> dict:
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
