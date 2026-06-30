"""Task routes: batch assignment, chunk upload, hash submission."""

from __future__ import annotations

import hashlib
import logging

import zstd
from config import Config
from constants import sanitize_filename
from db import Batch, Validation, get_db_session
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from routes.auth import verify_token
from s3_storage import create_storage_from_env
from sqlalchemy import select
from storage_manager import ChunkStorage
from tasker import attribute_tasks_to_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


class SubmitTasksRequest(BaseModel):
    batch_id: int
    chunk_hashes: dict[str, str]


@router.get("/batch")
async def get_batch(request: Request, token_data: dict = Depends(verify_token)):
    client_id = token_data.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="Invalid token payload")
    try:
        batch_id, region_coords = await attribute_tasks_to_client(client_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail="No tasks available") from err
    return JSONResponse({
        "batch_id": batch_id,
        "regions": [{"region_x": rx, "region_z": rz} for rx, rz in region_coords],
    })


@router.post("/submit")
async def submit_tasks(
    submit_tasks_request: SubmitTasksRequest,
    request: Request,
    token_data: dict = Depends(verify_token),
):
    batch_id = submit_tasks_request.batch_id
    chunk_hashes = submit_tasks_request.chunk_hashes
    results = {}
    storage = ChunkStorage()

    for filename, declared_hash in chunk_hashes.items():
        cached_hash = None
        async with get_db_session() as session:
            v_result = await session.execute(
                select(Validation).where(
                    Validation.batch_id == batch_id,
                    Validation.storage_path == filename,
                ).limit(1)
            )
            v = v_result.scalar_one_or_none()
            if v:
                cached_hash = v.file_hash

        if cached_hash:
            actual_hash = cached_hash
        else:
            data = storage.read_mca(filename)
            if data is None:
                results[filename] = {"status": "missing", "declared_hash": declared_hash}
                continue
            actual_hash = hashlib.sha256(data).hexdigest()

        if actual_hash == declared_hash:
            results[filename] = {"status": "valid", "hash": actual_hash}
        else:
            results[filename] = {
                "status": "mismatch",
                "declared_hash": declared_hash,
                "actual_hash": actual_hash,
            }

    valid_count = sum(1 for r in results.values() if r["status"] == "valid")
    total_count = len(results)
    all_valid = valid_count == total_count

    logger.info("hash validation: batch=%s valid=%s/%s", batch_id, valid_count, total_count)

    async with get_db_session() as session:
        batch_result = await session.execute(
            select(Batch).where(Batch.id == batch_id).limit(1)
        )
        batch = batch_result.scalar_one_or_none()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        batch.status = "completed" if all_valid else "hash_error"

        config = Config()
        if config.verification and all_valid:
            other_result = await session.execute(
                select(Batch).where(
                    Batch.id != batch_id,
                    Batch.region_x == batch.region_x,
                    Batch.region_z == batch.region_z,
                    Batch.status == "completed",
                ).limit(1)
            )
            other_batch = other_result.scalar_one_or_none()

            if other_batch:
                match = True
                for filename, info in results.items():
                    if info["status"] != "valid":
                        continue
                    other_hash = storage.get_mca_hash(filename)
                    if not other_hash or other_hash != info["hash"]:
                        match = False
                        break

                if match:
                    batch.status = "validated"
                    other_batch.status = "validated"
                    logger.info("batch validated: batch=%s other=%s", batch_id, other_batch.id)
                else:
                    batch.status = "hash_error"
                    other_batch.status = "hash_error"
                    batch.retry_count += 1
                    other_batch.retry_count += 1
                    logger.warning("redundancy mismatch: batch=%s other=%s", batch_id, other_batch.id)

        await session.commit()

    if all_valid:
        s3 = create_storage_from_env()
        if s3:
            try:
                s3.upload_batch(storage.regions_dir, batch_id)
                logger.info("batch uploaded to S3: batch=%s", batch_id)
            except Exception as e:
                logger.error("S3 upload failed: batch=%s error=%s", batch_id, e)

    return JSONResponse({"status": batch.status, "batch_id": batch_id, "results": results})


@router.put("/upload/{batch_id}")
async def upload_chunks(
    batch_id: int, request: Request, token_data: dict = Depends(verify_token)
):
    client_id = token_data.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="Invalid token payload")
    chunk_data = await request.body()
    try:
        decompressed_data = zstd.decompress(chunk_data)
        raw_filename = request.headers.get("X-Filename", "r.0.0.mca")
        try:
            filename = sanitize_filename(raw_filename)
        except ValueError as err:
            raise HTTPException(status_code=400, detail="Invalid filename") from err

        if not filename.endswith(".mca"):
            raise HTTPException(status_code=400, detail="Only .mca files accepted")

        storage = ChunkStorage()
        sha256_hash, raw_size = storage.write_mca(filename, decompressed_data)

        async with get_db_session() as session:
            existing = await session.execute(
                select(Validation).where(
                    Validation.batch_id == batch_id,
                    Validation.file_hash == sha256_hash,
                )
            )
            if not existing.scalar_one_or_none():
                session.add(Validation(
                    batch_id=batch_id,
                    client_id=client_id,
                    file_hash=sha256_hash,
                    storage_path=filename,
                ))

            batch_result = await session.execute(
                select(Batch).where(Batch.id == batch_id).limit(1)
            )
            batch = batch_result.scalar_one_or_none()
            if batch and batch.status == "assigned":
                batch.status = "working"
            await session.commit()

        logger.info(
            "upload: batch=%s file=%s hash=%s raw=%s compressed=%s",
            batch_id, filename, sha256_hash, raw_size, len(chunk_data),
        )
        return JSONResponse({
            "status": "received", "batch_id": batch_id,
            "filename": filename, "hash": sha256_hash,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("upload failed: batch=%s error=%s", batch_id, e)
        raise HTTPException(status_code=400, detail="Upload failed") from e
