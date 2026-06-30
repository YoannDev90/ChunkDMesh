"""Server routes: client heartbeat and benchmark."""

from __future__ import annotations

import datetime
import logging

from db import Client, get_db_session
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from routes.auth import verify_token
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(tags=["client"])


@router.post("/heartbeat")
async def heartbeat(request: Request, token_data: dict = Depends(verify_token)):
    client_id = token_data.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="Invalid token payload")

    async with get_db_session() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id).limit(1)
        )
        client = result.scalar_one_or_none()
        if client:
            client.last_seen = datetime.datetime.now(datetime.timezone.utc)
            await session.commit()

    return JSONResponse({"status": "ok"})


class BenchmarkRequest(BaseModel):
    chunks_per_second: float
    duration_seconds: float
    chunks_generated: int


@router.post("/benchmark")
async def submit_benchmark(req: BenchmarkRequest, request: Request, token_data: dict = Depends(verify_token)):
    client_id = token_data.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="Invalid token payload")

    score = req.chunks_per_second

    async with get_db_session() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id).limit(1)
        )
        client = result.scalar_one_or_none()
        if client:
            client.benchmark_score = score
            await session.commit()

    logger.info("benchmark submitted: client=%s chunks/s=%.2f", client_id, score)

    return JSONResponse({
        "status": "accepted",
        "chunks_per_second": score,
    })
