"""Modrinth API client for Chunky and Fabric API downloads."""

from __future__ import annotations

import httpx
from mc_utils import get_http_client

CHUNKY_MODRINTH_PROJECT_ID = "fALzjamp"
FABRIC_API_PROJECT_ID = "P7dR8mSH"


async def get_chunky_version(version: str, loader: str, minecraft_version: str | None = None) -> str | None:
    """Retrieves a specific Chunky version ID from Modrinth."""
    url = f"https://api.modrinth.com/v2/project/{CHUNKY_MODRINTH_PROJECT_ID}/version"
    if loader:
        url += f'?loaders=["{loader}"]'
    if minecraft_version:
        url += f'&game_versions=["{minecraft_version}"]'

    try:
        client = await get_http_client()
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

        if version is not None:
            for release in data:
                if version in release.get("version_number", ""):
                    return release.get("id")
            return None
        else:
            if not data:
                return None
            versions = {r.get("id"): r.get("downloads", 0) for r in data}
            sorted_v = sorted(versions.items(), key=lambda item: item[1], reverse=True)
            return sorted_v[0][0] if sorted_v else None
    except httpx.HTTPError as e:
        raise RuntimeError(f"Error connecting to Modrinth API: {e}") from e


async def get_modrinth_download(project_id: str, version: str, loader: str, minecraft_version: str) -> dict | None:
    """Get download info for a Modrinth project version.

    Returns {"url": ..., "filename": ..., "size": ...} or None.
    """
    url = f"https://api.modrinth.com/v2/project/{project_id}/version"
    params = {}
    if loader:
        params["loaders"] = f'["{loader}"]'
    if minecraft_version:
        params["game_versions"] = f'["{minecraft_version}"]'

    try:
        client = await get_http_client()
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        for release in data:
            if version and version in release.get("version_number", ""):
                files = release.get("files", [])
                if files:
                    f = files[0]
                    return {"url": f["url"], "filename": f["filename"], "size": f.get("size", 0)}

        if data:
            files = data[0].get("files", [])
            if files:
                f = files[0]
                return {"url": f["url"], "filename": f["filename"], "size": f.get("size", 0)}
        return None
    except httpx.HTTPError:
        return None


async def get_chunky_download(loader: str, minecraft_version: str, chunky_version: str) -> dict | None:
    return await get_modrinth_download(CHUNKY_MODRINTH_PROJECT_ID, chunky_version, loader, minecraft_version)


async def get_fabric_api_download(minecraft_version: str) -> dict | None:
    return await get_modrinth_download(FABRIC_API_PROJECT_ID, "", "fabric", minecraft_version)
