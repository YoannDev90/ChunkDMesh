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

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from typing import Optional, Dict, Generator
import os
from pathlib import Path
from pydantic import BaseModel
from jwt import encode, decode, PyJWTError
import logging
import uvicorn

app = FastAPI(title="ChunkDMesh Orchestrator", version="0.1.0", favicon="config/favicon.ico")
FAVICON_PATH = Path(__file__).resolve().parent / "config" / "favicon.ico"

def run_api_async():
	uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)

def file_stream_generator(path: str, chunk_size: int = 1024 * 64) -> Generator[bytes, None, None]:
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
async def root():
	return JSONResponse({"project": "ChunkDMesh", "status": "orchestrator", "message": "Welcome to ChunkDMesh API"})

@app.get("/health")
async def health():
	return JSONResponse({"status": "ok"})

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
	return FileResponse(FAVICON_PATH, media_type="image/x-icon")

@app.post("/auth/login")
async def login(login_request: LoginRequest):
	print(f"Received login with CPU cores: {login_request.cpu_cores}, RAM: {login_request.ram_gb} GB")
	return JSONResponse({"token": "dummy-jwt-token"})

@app.get("/assets/mods.zip")
async def get_mods():
	zip_path = "data/mods.zip"
	filename = os.path.basename(zip_path)
	headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
	return StreamingResponse(file_stream_generator(zip_path), media_type="application/zip", headers=headers)

@app.get("/assets/config.json")
async def get_config():
	from config import Config
	config = Config().__dict__()
	return JSONResponse(config)

@app.get("/tasks/batch")
async def get_batch():
	pass

@app.post("/tasks/submit")
async def submit_tasks():
	pass

@app.put("/tasks/upload/{batch_id}")
async def upload_chunks(batch_id: str):
	pass

@app.get("/admin/heatmap")
async def get_heatmap():
	pass

if __name__ == "__main__":
	import uvicorn
	uvicorn.run(app)