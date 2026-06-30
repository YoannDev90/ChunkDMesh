"""Asset routes: mods.zip, config.json."""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from pathlib import Path

from config import Config
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from routes.auth import verify_token

logger = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parent.parent.parent / "data"

router = APIRouter(prefix="/assets", tags=["assets"])


def _file_stream_generator(path: str, chunk_size: int = 1024 * 64) -> Generator[bytes, None, None]:
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk


@router.get("/mods.zip")
async def get_mods(request: Request, token_data: dict = Depends(verify_token)):
    zip_path = str(_DATA / "mods.zip")
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Mods not found")
    filename = os.path.basename(zip_path)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(_file_stream_generator(zip_path), media_type="application/zip", headers=headers)


@router.get("/config.json")
async def get_config(request: Request, token_data: dict = Depends(verify_token)):
    config = Config()
    await config.validate()
    return JSONResponse(config.to_dict())
