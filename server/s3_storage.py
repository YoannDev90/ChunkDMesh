"""S3/Cloudflare R2 storage driver for ChunkDMesh.

Supports AWS S3 and Cloudflare R2 (S3-compatible) for ephemeral deployments
where local disk is limited (Render, Vercel, etc.).

Requires: boto3 (add to requirements.txt if using this module).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class S3Storage:
    def __init__(
        self,
        bucket: str,
        endpoint_url: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        region: str = "auto",
        prefix: str = "",
    ):
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._endpoint_url = endpoint_url
        self._access_key = aws_access_key_id
        self._secret_key = aws_secret_access_key
        self._region = region
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            import boto3
        except ImportError:
            raise RuntimeError("boto3 is required for S3 storage. Install with: pip install boto3")

        kwargs = {"region_name": self._region}
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url
        if self._access_key:
            kwargs["aws_access_key_id"] = self._access_key
        if self._secret_key:
            kwargs["aws_secret_access_key"] = self._secret_key

        self._client = boto3.client("s3", **kwargs)
        return self._client

    def upload_file(self, local_path: Path, key: str) -> str:
        client = self._get_client()
        full_key = self.prefix + key

        logger.info("Uploading %s -> s3://%s/%s", local_path, self.bucket, full_key)
        client.upload_file(str(local_path), self.bucket, full_key)

        return f"s3://{self.bucket}/{full_key}"

    def upload_batch(self, batch_dir: Path, batch_id: int) -> list[str]:
        urls = []
        for mca_file in batch_dir.glob("*.mca"):
            key = f"batches/{batch_id}/{mca_file.name}"
            url = self.upload_file(mca_file, key)
            urls.append(url)
        return urls

    def download_file(self, key: str, local_path: Path) -> Path:
        client = self._get_client()
        full_key = self.prefix + key

        local_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading s3://%s/%s -> %s", self.bucket, full_key, local_path)
        client.download_file(self.bucket, full_key, str(local_path))
        return local_path

    def delete_file(self, key: str):
        client = self._get_client()
        full_key = self.prefix + key
        logger.info("Deleting s3://%s/%s", self.bucket, full_key)
        client.delete_object(Bucket=self.bucket, Key=full_key)

    def list_files(self, prefix: str = "") -> list[str]:
        client = self._get_client()
        full_prefix = self.prefix + prefix

        response = client.list_objects_v2(Bucket=self.bucket, Prefix=full_prefix)
        return [obj["Key"] for obj in response.get("Contents", [])]

    def presign_url(self, key: str, expiration: int = 3600) -> str:
        client = self._get_client()
        full_key = self.prefix + key

        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": full_key},
            ExpiresIn=expiration,
        )
        return url


def create_storage_from_env() -> Optional[S3Storage]:
    import os

    bucket = os.environ.get("CHUNKDMESH_S3_BUCKET")
    if not bucket:
        return None

    return S3Storage(
        bucket=bucket,
        endpoint_url=os.environ.get("CHUNKDMESH_S3_ENDPOINT"),
        aws_access_key_id=os.environ.get("CHUNKDMESH_S3_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("CHUNKDMESH_S3_SECRET_KEY"),
        region=os.environ.get("CHUNKDMESH_S3_REGION", "auto"),
        prefix=os.environ.get("CHUNKDMESH_S3_PREFIX", "chunkdmesh"),
    )
