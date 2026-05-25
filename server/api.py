import logging
import uuid
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File, Form
from pydantic import BaseModel

import config
from database import Database, Type
from world_assembler import assemble_world

LOGGER = logging.getLogger(config.LOGGER_NAME)

app = FastAPI(title="ChunkDMesh API", version="1.0.0")

# --- Modèles Pydantic ---


class Task(BaseModel):
    task_id: int
    x: int
    z: int


class TaskResponse(BaseModel):
    batch_id: int
    tasks: List[Task]
    seed: Optional[int]
    shape: str
    pattern: str


class IndividualResult(BaseModel):
    task_id: int
    signature: str
    data_path: Optional[str] = None


class SubmitRequest(BaseModel):
    results: List[IndividualResult]


# --- Dépendances ---


async def get_db():
    async with Database(config.DB_PATH) as db:
        yield db


async def get_current_client(request: Request, db: Database = Depends(get_db)):
    token = request.headers.get("X-Client-Token")
    if not token:
        raise HTTPException(status_code=401, detail="X-Client-Token header missing")

    clients = await db.execute_query(
        "SELECT id FROM clients WHERE token = ?", (token,), type=Type.LIST
    )
    if not clients:
        raise HTTPException(status_code=401, detail="Invalid token")
    return clients[0]


# --- Routes ---


@app.get("/connect")
async def connect(request: Request, db: Database = Depends(get_db)):
    """Enregistre un nouveau client et renvoie un token unique."""
    client_ip = request.client.host
    token = str(uuid.uuid4())

    await db.execute_query(
        "INSERT INTO clients (token, ip_address) VALUES (?, ?)", (token, client_ip)
    )

    LOGGER.info(f"Nouveau client connecté : {client_ip} (Token: {token[:8]}...)")
    return {"message": "Connexion réussie", "token": token}


@app.get("/status")
async def get_status(db: Database = Depends(get_db)):
    """Renvoie le statut global de l'orchestrateur."""
    connected_count = await db.execute_query(
        "SELECT COUNT(*) FROM clients", type=Type.LIST
    )
    return {
        "status": "API en cours d'exécution",
        "connected_clients": connected_count[0] if connected_count else 0,
    }


@app.get("/get_task", response_model=TaskResponse)
async def get_task(
    client_id: int = Depends(get_current_client), db: Database = Depends(get_db)
):
    """Récupère un lot de chunks à traiter."""
    current_config = config.load_config()
    batch_size = current_config.batch_size
    verification_enabled = current_config.verification

    if verification_enabled:
        query = """
        SELECT t.id, t.x, t.z 
        FROM tasks t
        LEFT JOIN results r ON t.id = r.task_id
        WHERE t.status IN ('PENDING', 'IN_PROGRESS')
        AND t.id NOT IN (SELECT task_id FROM results WHERE client_id = ?)
        GROUP BY t.id
        HAVING COUNT(DISTINCT r.client_id) < 2
        LIMIT ?
        """
        params = (client_id, batch_size)
    else:
        query = "SELECT id, x, z FROM tasks WHERE status = 'PENDING' LIMIT ?"
        params = (batch_size,)

    tasks_raw = await db.execute_query(query, params, type=Type.TUPLE)

    if not tasks_raw:
        raise HTTPException(status_code=404, detail="Aucune tâche disponible")

    task_ids = [t[0] for t in tasks_raw]
    placeholders = ",".join(["?"] * len(task_ids))
    await db.execute_query(
        f"UPDATE tasks SET status = 'IN_PROGRESS' WHERE id IN ({placeholders})",
        tuple(task_ids),
    )

    tasks = [Task(task_id=t[0], x=t[1], z=t[2]) for t in tasks_raw]

    return TaskResponse(
        batch_id=tasks[0].task_id,
        tasks=tasks,
        seed=current_config.seed,
        shape=current_config.shape,
        pattern=current_config.pattern,
    )


@app.post("/submit_result")
async def submit_result(
    request: Request,
    client_id: int = Depends(get_current_client),
    db: Database = Depends(get_db),
):
    """Soumet les résultats (signatures et fichiers)."""
    current_config = config.load_config()
    storage_dir = (
        config.ACTIVE_CONFIG_PATH.parent / "world_storage" / current_config.world_name
    )
    storage_dir.mkdir(parents=True, exist_ok=True)

    results_to_process = []
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        data = await request.json()
        results_to_process = data.get("results", [])
    elif "multipart/form-data" in content_type:
        form = await request.form()
        file = form.get("file")
        task_id = form.get("task_id")
        signature = form.get("signature")

        if task_id and file:
            task_info = await db.execute_query(
                "SELECT x, z FROM tasks WHERE id = ?", (task_id,), type=Type.TUPLE
            )
            if task_info:
                x, z = task_info[0]
                file_path = storage_dir / f"{x}_{z}.mca"
                with open(file_path, "wb") as f:
                    f.write(await file.read())
                results_to_process = [
                    {
                        "task_id": int(task_id),
                        "signature": signature,
                        "data_path": str(file_path),
                    }
                ]

    for res in results_to_process:
        t_id = res.get("task_id")
        sig = res.get("signature")
        path = res.get("data_path")

        await db.execute_query(
            "INSERT INTO results (task_id, client_id, signature, data_path) VALUES (?, ?, ?, ?)",
            (t_id, client_id, sig, path),
        )

        all_results = await db.execute_query(
            "SELECT signature FROM results WHERE task_id = ?", (t_id,), type=Type.LIST
        )

        if current_config.verification:
            if len(all_results) >= 2:
                if all_results[0] == all_results[1]:
                    await db.execute_query(
                        "UPDATE tasks SET status = 'VALIDATED' WHERE id = ?", (t_id,)
                    )
                else:
                    await db.execute_query(
                        "UPDATE tasks SET status = 'FAILED' WHERE id = ?", (t_id,)
                    )
        else:
            await db.execute_query(
                "UPDATE tasks SET status = 'VALIDATED' WHERE id = ?", (t_id,)
            )

    return {
        "message": f"{len(results_to_process)} résultats traités",
        "status": "success",
    }


@app.get("/assemble")
async def trigger_assembly():
    """Déclenche l'assemblage final du monde."""
    current_config = config.load_config()
    try:
        path = await assemble_world(current_config.world_name)
        return {"message": "Assemblage terminé", "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
