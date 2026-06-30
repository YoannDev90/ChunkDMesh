"""Shared constants for the ChunkDMesh server."""

from __future__ import annotations

import hashlib
import secrets
import string
from pathlib import Path, PurePosixPath

RCON_PORT = 25575
RCON_PASSWORD_LENGTH = 32
DEFAULT_PORT = 8000
JWT_EXPIRY_HOURS = 24
HEARTBEAT_INTERVAL_SECONDS = 15
HEARTBEAT_TIMEOUT_SECONDS = 60
TILE_CACHE_MAX_SIZE = 500
RECENT_REQUESTS_MAX = 50


def generate_rcon_password() -> str:
    """Generate a secure random RCON password."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(RCON_PASSWORD_LENGTH))


def sanitize_filename(name: str) -> str:
    """Reject path traversal attempts. Returns only the basename."""
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"Invalid filename: {name}")
    return p.name


def compute_file_hash(path: str | Path, chunk_size: int = 1024 * 64) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
