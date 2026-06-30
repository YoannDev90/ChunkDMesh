"""Minecraft version fetching from Mojang's manifest API."""

from __future__ import annotations

import time

import httpx
from mc_utils import get_http_client

CACHE_DURATION_SECONDS = 3600
_latest_mc_version_value: str | None = None
_latest_mc_version_timestamp: float = 0.0


async def get_latest_minecraft_release_version() -> str:
    """Retrieves the latest Minecraft release version, cached for 1 hour."""
    global _latest_mc_version_value, _latest_mc_version_timestamp
    current_time = time.time()
    if _latest_mc_version_value and (current_time - _latest_mc_version_timestamp) < CACHE_DURATION_SECONDS:
        return _latest_mc_version_value

    versions = await get_minecraft_versions(version_type="release")
    if versions:
        latest = versions[0]
        _latest_mc_version_value = latest
        _latest_mc_version_timestamp = current_time
        return latest

    raise RuntimeError("Could not retrieve latest Minecraft release version")


async def get_minecraft_versions(version_type: str | None = None) -> list[str]:
    """Retrieves Minecraft versions from Mojang's manifest, optionally filtered by type."""
    if version_type and version_type not in ["release", "snapshot"]:
        raise ValueError("Invalid version type. Must be 'release', 'snapshot', or None.")

    try:
        client = await get_http_client()
        response = await client.get("https://piston-meta.mojang.com/mc/game/version_manifest.json")
        response.raise_for_status()
        data = response.json()
        return [v["id"] for v in data.get("versions", []) if not version_type or v.get("type") == version_type]
    except httpx.HTTPError as e:
        raise RuntimeError(f"Error connecting to Mojang API: {e}") from e
