import asyncio
import re
import time
import xml.etree.ElementTree as ET
from typing import List, Optional

import httpx

http_client = httpx.AsyncClient()

_latest_mc_version_cache = {"value": None, "timestamp": 0}
CACHE_DURATION_SECONDS = 3600  # 1 hour


async def get_latest_minecraft_release_version() -> str:
    """
    Retrieves the latest Minecraft release version, using a cache to avoid frequent API calls.
    """
    global _latest_mc_version_cache
    current_time = time.time()

    if (
        _latest_mc_version_cache["value"]
        and (current_time - _latest_mc_version_cache["timestamp"])
        < CACHE_DURATION_SECONDS
    ):
        return _latest_mc_version_cache["value"]

    versions = await get_minecraft_versions(version_type="release")
    if versions:
        latest = versions[0]
        _latest_mc_version_cache = {"value": latest, "timestamp": current_time}
        return latest

    raise RuntimeError("Could not retrieve latest Minecraft release version")


async def get_minecraft_versions(version_type: Optional[str] = None) -> List[str]:
    """
    Retrieves a list of Minecraft versions from Mojang's manifest, with optional filtering by type.
    """
    if version_type and version_type not in ["release", "snapshot"]:
        raise ValueError(
            "Invalid version type. Must be 'release', 'snapshot', or None."
        )

    try:
        response = await http_client.get(
            "https://piston-meta.mojang.com/mc/game/version_manifest.json"
        )
        response.raise_for_status()
        data = response.json()

        return [
            version["id"]
            for version in data.get("versions", [])
            if not version_type or version.get("type") == version_type
        ]
    except httpx.HTTPError as e:
        raise RuntimeError(f"Error connecting to Mojang API: {e}")


async def get_fabric_versions(minecraft_version: Optional[str] = None) -> List[str]:
    """
    Retrieves a list of Fabric loader versions for a given Minecraft version or the latest release version.
    """
    target_mc_version = (
        minecraft_version or await get_latest_minecraft_release_version()
    )

    try:
        response = await http_client.get(
            f"https://meta.fabricmc.net/v2/versions/loader/{target_mc_version}"
        )
        response.raise_for_status()
        data = response.json()

        return [
            item["loader"]["version"]
            for item in data
            if "loader" in item and "version" in item["loader"]
        ]
    except httpx.HTTPError as e:
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
            return []
        raise RuntimeError(f"Error connecting to Fabric API: {e}")


async def get_quilt_versions() -> List[str]:
    """
    Retrieves a list of stable Quilt loader versions by parsing their Maven metadata XML.
    """
    try:
        response = await http_client.get(
            "https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-loader/maven-metadata.xml"
        )
        response.raise_for_status()

        root = ET.fromstring(response.text)
        versions_element = root.find(".//versions")

        if versions_element is None:
            return []

        stable_versions = [
            v.text
            for v in versions_element.findall("version")
            if v.text and "-beta" not in v.text and "-pre" not in v.text
        ]

        stable_versions.sort(
            key=lambda s: [
                int(u) if u.isdigit() else u for u in re.split("([0-9]+)", s)
            ],
            reverse=True,
        )
        return stable_versions
    except (httpx.HTTPError, ET.ParseError) as e:
        raise RuntimeError(f"Error fetching/parsing Quilt versions: {e}")


async def get_forge_versions(
    minecraft_version: Optional[str] = None, version_only: bool = False
) -> List[str]:
    """
    Retrieves a list of Forge versions for a given Minecraft version or the latest release version.
    """
    target_mc_version = (
        minecraft_version or await get_latest_minecraft_release_version()
    )

    try:
        response = await http_client.get(
            "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"
        )
        response.raise_for_status()

        root = ET.fromstring(response.text)
        versions_element = root.find(".//versions")

        if versions_element is None:
            return []

        filtered = []
        prefix = f"{target_mc_version}-"
        for v_elem in versions_element.findall("version"):
            version = v_elem.text
            if version and version.startswith(prefix):
                if version_only:
                    filtered.append(version.split(prefix, 1)[-1])
                else:
                    filtered.append(version)
        return filtered
    except (httpx.HTTPError, ET.ParseError) as e:
        raise RuntimeError(f"Error fetching/parsing Forge versions: {e}")


async def get_neoforge_versions(
    minecraft_version: Optional[str] = None, version_type: Optional[str] = None
) -> List[str]:
    """
    Retrieves a list of NeoForge versions by parsing their Maven metadata XML.
    """
    if version_type and version_type not in ["release"]:
        raise ValueError("Invalid NeoForge version type. Must be 'release' or None.")

    try:
        response = await http_client.get(
            "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
        )
        response.raise_for_status()

        root = ET.fromstring(response.text)
        versions_element = root.find(".//versions")

        if versions_element is None:
            return []

        neoforge_versions = []
        for v_elem in versions_element.findall("version"):
            version = v_elem.text
            if version:
                if version_type == "release" and "-beta" in version:
                    continue
                neoforge_versions.append(version)

        neoforge_versions.reverse()
        return neoforge_versions
    except (httpx.HTTPError, ET.ParseError) as e:
        raise RuntimeError(f"Error fetching/parsing NeoForge versions: {e}")


async def get_chunky_version(
    version: str, loader: str, minecraft_version: Optional[str] = None
) -> str:
    """
    Retrieves a specific Chunky version by parsing Modrinth's API.
    """

    CHUNKY_MODRINTH_PROJECT_ID = "fALzjamp"

    url = f"https://api.modrinth.com/v2/project/{CHUNKY_MODRINTH_PROJECT_ID}/version"
    if loader:
        url += f'?loaders=["{loader}"]'
    if minecraft_version:
        url += f'&game_versions=["{minecraft_version}"]'

    try:
        response = await http_client.get(url)
        response.raise_for_status()
        data = response.json()

        if version is not None:
            for release in data:
                version_data = release.get("version_number", "")
                if version in version_data:
                    return release.get("id")
            return None
        else:
            if not data:
                return None
            versions = {
                release.get("id"): release.get("downloads", 0) for release in data
            }
            sorted_versions = sorted(
                versions.items(), key=lambda item: item[1], reverse=True
            )
            return sorted_versions[0][0] if sorted_versions else None

    except httpx.HTTPError as e:
        raise RuntimeError(f"Error connecting to Modrinth API: {e}")


FABRIC_API_PROJECT_ID = "P7dR8mSH"

CHUNKY_MODRINTH_PROJECT_ID = "fALzjamp"


async def get_modrinth_download(
    project_id: str, version: str, loader: str, minecraft_version: str
) -> Optional[dict]:
    """
    Get download info for a Modrinth project version.
    Returns {"url": ..., "filename": ..., "size": ...} or None.
    """
    url = f"https://api.modrinth.com/v2/project/{project_id}/version"
    params = {}
    if loader:
        params["loaders"] = f'["{loader}"]'
    if minecraft_version:
        params["game_versions"] = f'["{minecraft_version}"]'

    try:
        response = await http_client.get(url, params=params)
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


async def get_chunky_download(loader: str, minecraft_version: str, chunky_version: str) -> Optional[dict]:
    return await get_modrinth_download(
        CHUNKY_MODRINTH_PROJECT_ID, chunky_version, loader, minecraft_version
    )


async def get_fabric_api_download(minecraft_version: str) -> Optional[dict]:
    return await get_modrinth_download(
        FABRIC_API_PROJECT_ID, "", "fabric", minecraft_version
    )


async def get_loader_version(
    loader: str, minecraft_version: Optional[str] = None
) -> list:
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
