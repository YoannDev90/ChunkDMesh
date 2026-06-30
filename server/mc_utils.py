"""Shared HTTP client and loader version dispatcher."""

from __future__ import annotations

import httpx

_http_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    """Get or create the shared async HTTP client."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient()
    return _http_client


async def get_loader_version(
    loader: str, minecraft_version: str | None = None
) -> list[str]:
    """Dispatcher: fetch compatible versions for the given loader."""
    from mc_loaders import (
        get_fabric_versions,
        get_forge_versions,
        get_neoforge_versions,
        get_quilt_versions,
    )

    if loader == "forge":
        return await get_forge_versions(minecraft_version)
    elif loader == "fabric":
        return await get_fabric_versions(minecraft_version)
    elif loader == "quilt":
        return await get_quilt_versions()
    elif loader == "neoforge":
        return await get_neoforge_versions(minecraft_version)
    else:
        raise ValueError(f"Unsupported loader type: {loader}")
