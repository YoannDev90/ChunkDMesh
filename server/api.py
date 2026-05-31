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
import logging
import os
from pathlib import Path
from typing import Dict, Generator, Optional

import uvicorn
from config import ChunkyPattern, ChunkyShape, Config
from db import Batch, Client, Validation, World, get_db_session
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from jwt import PyJWTError, decode, encode
from pydantic import BaseModel

app = FastAPI(
    title="ChunkDMesh Orchestrator", version="0.1.0", favicon="config/favicon.ico"
)
FAVICON_PATH = Path(__file__).resolve().parent / "config" / "favicon.ico"


def run_api_async():
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)


def generate_sk_key():
    import secrets

    key = secrets.token_hex(64)
    key_path = Path(__file__).resolve().parent / "config" / "key.pem"
    key_path.write_text(key)
    return key


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


@app.get("/")
async def root(request: Request):
    return JSONResponse(
        {
            "project": "ChunkDMesh",
            "status": "orchestrator",
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
    key_path = Path(__file__).resolve().parent / "config" / "key.pem"
    if key_path.exists() and key_path.is_file():
        sk_key = key_path.read_text()
    else:
        sk_key = generate_sk_key()
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
async def get_mods(request: Request):
    zip_path = "data/mods.zip"
    filename = os.path.basename(zip_path)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        file_stream_generator(zip_path), media_type="application/zip", headers=headers
    )


@app.get("/assets/config.json")
async def get_config(request: Request):
    from config import Config

    config = Config().__dict__()
    return JSONResponse(config)


@app.get("/tasks/batch")
async def get_batch(request: Request):
    pass


@app.post("/tasks/submit")
async def submit_tasks(request: Request):
    pass


@app.put("/tasks/upload/{batch_id}")
async def upload_chunks(batch_id: str, request: Request):
    pass


@app.get("/admin/heatmap")
async def get_heatmap(request: Request):
    pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)
