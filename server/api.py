"""FastAPI API entrypoint for ChunkDMesh orchestrator.

- GET / : basic project info
- GET /docs : API documentation (OpenAPI spec)
- GET /health : health check
- POST /auth/login : Le client envoie ses capacités (CPU, RAM disponible) et reçoit un token JWT.
- GET /assets/mods.zip : Streaming de l'archive des mods (avec support du header `Range`).
- GET /assets/config.json : Configuration spécifique de Chunky pour cette session.
- GET /tasks/batch : Récupère un lot de chunks. Le serveur marque le batch comme `ASSIGNED`.
- POST /tasks/submit : Envoie les hashes SHA-256 de chaque chunk généré.
- PUT /tasks/upload/{batch_id} : Upload binaire des données de chunks (compressées en Zstd).
- GET /admin/heatmap : Renvoie une matrice de l'état du monde pour le dashboard.
"""

import datetime
import hashlib
import logging
import os
from pathlib import Path
from typing import Dict, Generator, Optional

import uvicorn
import zstd
from config import ChunkyPattern, ChunkyShape, Config
from db import Batch, Client, Validation, World, get_db_session
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from jwt import PyJWTError, decode, encode
from logging_utils import ulog
from pydantic import BaseModel

app = FastAPI(
    title="ChunkDMesh Orchestrator", version="0.1.0", favicon="config/favicon.ico"
)
FAVICON_PATH = Path(__file__).resolve().parent / "config" / "favicon.ico"


async def run_api():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def get_secret_key():
    key_path = Path(__file__).resolve().parent / "config" / "key.pem"
    if key_path.exists():
        return key_path.read_text().strip()
    
    import secrets
    key = secrets.token_hex(64)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(key)
    return key


async def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = authorization.split(" ")[1]
    sk_key = get_secret_key()
    try:
        payload = decode(token, sk_key, algorithms=["HS256"])
        return payload
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def file_stream_generator(
    path: str, chunk_size: int = 1024 * 64
) -> Generator[bytes, None, None]:
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk


class LoginRequest(BaseModel):
    cpu_cores: int
    ram_gb: int


class SubmitTasksRequest(BaseModel):
    batch_id: int
    chunk_hashes: Dict[str, str]  # {"chunk_x_z": "sha256hash"}


@app.get("/")
async def root(request: Request):
    return JSONResponse(
        {
            "project": "ChunkDMesh",
            "message": "Welcome to ChunkDMesh API",
        }
    )


@app.get("/health")
async def health(request: Request):
    return JSONResponse({"status": "ok"})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(FAVICON_PATH, media_type="image/x-icon")


@app.post("/auth/login")
async def login(login_request: LoginRequest, request: Request):
    payload = {
        "client_ip": request.client.host,
        "timestamp": int(datetime.datetime.now().timestamp()),
        "cpu_cores": login_request.cpu_cores,
        "ram_gb": login_request.ram_gb,
    }
    sk_key = get_secret_key()
    jwt_token = encode(payload, sk_key, algorithm="HS256")
    async with get_db_session() as session:
        session.add(
            Client(
                token=jwt_token,
                ip=request.client.host,
                cpu_cores=login_request.cpu_cores,
                ram_gb=login_request.ram_gb,
            )
        )
        await session.commit()

    return JSONResponse({"token": jwt_token})


@app.get("/assets/mods.zip")
async def get_mods(request: Request, token_data: dict = Depends(verify_token)):
    zip_path = "data/mods.zip"
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Mods not found")
    filename = os.path.basename(zip_path)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        file_stream_generator(zip_path), media_type="application/zip", headers=headers
    )


@app.get("/assets/config.json")
async def get_config(request: Request, token_data: dict = Depends(verify_token)):
    from config import Config

    config = Config()
    await config.validate()
    config_dict = config.to_dict()
    return JSONResponse(config_dict)


@app.get("/tasks/batch")
async def get_batch(request: Request, token_data: dict = Depends(verify_token)):
    from tasker import attribute_tasks_to_client
    client_id = token_data.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="Invalid token payload")
    batch_id, region_coords = await attribute_tasks_to_client(client_id)
    batch = {
        "batch_id": batch_id,
        "regions": [{"region_x": rx, "region_z": rz} for rx, rz in region_coords],
    }
    return JSONResponse(batch)


@app.post("/tasks/submit")
async def submit_tasks(submit_tasks_request: SubmitTasksRequest, request: Request, token_data: dict = Depends(verify_token)):
    ulog(
        logging.INFO,
        "submit_tasks_received",
        batch_id=submit_tasks_request.batch_id,
        chunk_hashes=submit_tasks_request.chunk_hashes,
    )
    return JSONResponse(
        {"status": "received", "batch_id": submit_tasks_request.batch_id}
    )


@app.put("/tasks/upload/{batch_id}")
async def upload_chunks(
    batch_id: int, request: Request, token_data: dict = Depends(verify_token)
):
    chunk_data = await request.body()
    # decompress chunk_data with Zstd and save to disk (for testing)
    try:
        decompressed_data = zstd.decompress(chunk_data)
        sha256_hash = hashlib.sha256(decompressed_data).hexdigest()
        ulog(
            logging.INFO,
            "upload_chunks_received",
            batch_id=batch_id,
            sha256_hash=sha256_hash,
            chunk_size=len(chunk_data),
        )
        return JSONResponse({"status": "received", "batch_id": batch_id})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Decompression failed: {str(e)}")



@app.get("/admin/heatmap")
async def get_heatmap(request: Request):
    pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)
