"""Auth routes: login, token verification, secret key management."""

from __future__ import annotations

import datetime
import logging
import os
import secrets
import threading
from pathlib import Path

from constants import JWT_EXPIRY_HOURS
from db import Client, get_db_session
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from jwt import ExpiredSignatureError, PyJWTError, decode, encode
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_SRV = Path(__file__).resolve().parent.parent

_secret_key_cache: str | None = None
_secret_key_lock = threading.Lock()


def get_secret_key() -> str:
    """Load or generate JWT secret key from config/key.pem."""
    global _secret_key_cache
    if _secret_key_cache is not None:
        return _secret_key_cache

    with _secret_key_lock:
        if _secret_key_cache is not None:
            return _secret_key_cache
        key_path = _SRV / "config" / "key.pem"
        if key_path.exists():
            _secret_key_cache = key_path.read_text().strip()
            return _secret_key_cache

        key = secrets.token_hex(64)
        key_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, key.encode())
        finally:
            os.close(fd)
        _secret_key_cache = key
        return key


async def verify_token(authorization: str | None = Header(None)):
    """Verify JWT token from Authorization header. Returns decoded payload."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = authorization.split(" ")[1]
    sk_key = get_secret_key()
    try:
        payload = decode(token, sk_key, algorithms=["HS256"], options={"require": ["exp"]})
        return payload
    except ExpiredSignatureError as err:
        raise HTTPException(status_code=401, detail="Token expired") from err
    except PyJWTError as err:
        raise HTTPException(status_code=401, detail="Invalid token") from err


class LoginRequest(BaseModel):
    """Client login payload with power score."""

    power_score: float


@router.post("/login")
async def login(login_request: LoginRequest, request: Request):
    """Register client and return JWT token."""
    sk_key = get_secret_key()
    async with get_db_session() as session:
        client = Client(
            token=None,
            ip=request.client.host,
            power_score=login_request.power_score,
        )
        session.add(client)
        await session.flush()

        now = datetime.datetime.now(datetime.timezone.utc)
        payload = {
            "client_id": client.id,
            "client_ip": request.client.host,
            "timestamp": int(now.timestamp()),
            "power_score": login_request.power_score,
            "exp": now + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
            "iat": now,
        }
        jwt_token = encode(payload, sk_key, algorithm="HS256")
        client.token = jwt_token
        await session.commit()

    return JSONResponse({"token": jwt_token})
