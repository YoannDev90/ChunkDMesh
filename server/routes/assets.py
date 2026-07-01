"""Asset routes: mods.zip, config.json, mcmap binaries."""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from pathlib import Path

from config import Config
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from routes.auth import verify_token

logger = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parent.parent.parent / "data"
_BIN = Path(__file__).resolve().parent.parent.parent / "bin"

router = APIRouter(prefix="/assets", tags=["assets"])

# Map (os, arch) to binary name
_TARGET_MAP = {
    ("linux", "x86_64"): "linux-amd64",
    ("linux", "aarch64"): "linux-arm64",
    ("linux", "armv7l"): "linux-armv7",
    ("darwin", "x86_64"): "macos-amd64",
    ("darwin", "arm64"): "macos-arm64",
    ("win32", "amd64"): "windows-amd64.exe",
}


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


@router.get("/mcmap/list")
async def list_mcmap_binaries():
    """List available pre-compiled mcmap binaries."""
    _BIN.mkdir(parents=True, exist_ok=True)
    binaries = []
    for f in sorted(_BIN.glob("mcmap-*")):
        if f.is_file():
            friendly = f.name.removeprefix("mcmap-")
            binaries.append({"target": friendly, "filename": f.name, "size": f.stat().st_size})
    return JSONResponse({"binaries": binaries})


@router.get("/mcmap/{target}")
async def get_mcmap_binary(target: str, token_data: dict = Depends(verify_token)):
    """Download a pre-compiled mcmap binary for a specific target."""
    _BIN.mkdir(parents=True, exist_ok=True)
    binary = _BIN / f"mcmap-{target}"
    if not binary.exists():
        raise HTTPException(status_code=404, detail=f"Binary not found for target: {target}")
    return FileResponse(binary, media_type="application/octet-stream", filename=f"mcmap-{target}")


@router.get("/mcmap/detect/{os_name}/{arch}")
async def detect_mcmap_binary(os_name: str, arch: str, token_data: dict = Depends(verify_token)):
    """Check if a pre-compiled binary exists for the given OS/arch."""
    target = _TARGET_MAP.get((os_name, arch))
    if not target:
        return JSONResponse({"available": False, "reason": f"Unsupported platform: {os_name}/{arch}"})
    binary = _BIN / f"mcmap-{target}"
    return JSONResponse(
        {
            "available": binary.exists(),
            "target": target,
            "filename": f"mcmap-{target}",
            "size": binary.stat().st_size if binary.exists() else 0,
        }
    )
