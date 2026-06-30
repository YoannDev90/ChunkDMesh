"""Loader version fetching and installation configs for Fabric, Forge, Quilt, NeoForge."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx
from mc_utils import get_http_client
from mc_versions import get_latest_minecraft_release_version


@dataclass(frozen=True)
class LoaderConfig:
    """Complete install + download configuration for a mod loader."""

    name: str
    install_url_template: str
    installer_jar_template: str | None
    installer_args: list[str]
    installed_jar_patterns: list[str]
    version_url: str
    version_filter: str | None = None


LOADER_CONFIGS: dict[str, LoaderConfig] = {
    "fabric": LoaderConfig(
        name="fabric",
        install_url_template="https://meta.fabricmc.net/v2/versions/loader/{mc_version}/{loader_version}/1.0.0/server/jar",
        installer_jar_template=None,
        installer_args=[],
        installed_jar_patterns=["fabric-server-mc.{mc_version}-loader.{loader_version}-launcher.{mc_version}.jar"],
        version_url="https://meta.fabricmc.net/v2/versions/loader/{mc_version}",
    ),
    "forge": LoaderConfig(
        name="forge",
        install_url_template="https://maven.minecraftforge.net/net/minecraftforge/forge/{mc_version}-{loader_version}/forge-{mc_version}-{loader_version}-installer.jar",
        installer_jar_template="forge-{mc_version}-{loader_version}-installer.jar",
        installer_args=[],
        installed_jar_patterns=[
            "forge-{mc_version}-{loader_version}.jar",
            "forge-{mc_version}-{loader_version}-universal.jar",
            "forge-{mc_version}-{loader_version}-server.jar",
        ],
        version_url="https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml",
        version_filter="forge",
    ),
    "quilt": LoaderConfig(
        name="quilt",
        install_url_template="https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-installer/{loader_version}/quilt-installer-{loader_version}.jar",
        installer_jar_template="quilt-server-installer-{loader_version}.jar",
        installer_args=["--install-server"],
        installed_jar_patterns=[
            "quilt-server-{loader_version}.jar",
            "quilt-server-mc.{mc_version}-ql.{loader_version}.jar",
        ],
        version_url="https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-loader/maven-metadata.xml",
        version_filter="quilt",
    ),
    "neoforge": LoaderConfig(
        name="neoforge",
        install_url_template="https://maven.neoforged.net/releases/net/neoforged/neoforge/{loader_version}/neoforge-{mc_version}-{loader_version}-installer.jar",
        installer_jar_template="neoforge-{mc_version}-{loader_version}-installer.jar",
        installer_args=["--install-server"],
        installed_jar_patterns=[
            "neoforge-{mc_version}-{loader_version}.jar",
            "neoforge-{mc_version}-{loader_version}-universal.jar",
        ],
        version_url="https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml",
        version_filter="neoforge",
    ),
}


async def get_fabric_versions(minecraft_version: str | None = None) -> list[str]:
    target = minecraft_version or await get_latest_minecraft_release_version()
    try:
        client = await get_http_client()
        response = await client.get(f"https://meta.fabricmc.net/v2/versions/loader/{target}")
        response.raise_for_status()
        data = response.json()
        return [item["loader"]["version"] for item in data if "loader" in item and "version" in item["loader"]]
    except httpx.HTTPError as e:
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
            return []
        raise RuntimeError(f"Error connecting to Fabric API: {e}") from e


async def get_quilt_versions() -> list[str]:
    try:
        client = await get_http_client()
        response = await client.get(
            "https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-loader/maven-metadata.xml"
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
        versions_element = root.find(".//versions")
        if versions_element is None:
            return []
        stable = [
            v.text
            for v in versions_element.findall("version")
            if v.text and "-beta" not in v.text and "-pre" not in v.text
        ]
        stable.sort(key=lambda s: [int(u) if u.isdigit() else u for u in re.split("([0-9]+)", s)], reverse=True)
        return stable
    except (httpx.HTTPError, ET.ParseError) as e:
        raise RuntimeError(f"Error fetching/parsing Quilt versions: {e}") from e


async def get_forge_versions(minecraft_version: str | None = None, version_only: bool = False) -> list[str]:
    target = minecraft_version or await get_latest_minecraft_release_version()
    try:
        client = await get_http_client()
        response = await client.get("https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml")
        response.raise_for_status()
        root = ET.fromstring(response.text)
        versions_element = root.find(".//versions")
        if versions_element is None:
            return []
        prefix = f"{target}-"
        filtered = []
        for v_elem in versions_element.findall("version"):
            version = v_elem.text
            if version and version.startswith(prefix):
                filtered.append(version.split(prefix, 1)[-1] if version_only else version)
        return filtered
    except (httpx.HTTPError, ET.ParseError) as e:
        raise RuntimeError(f"Error fetching/parsing Forge versions: {e}") from e


async def get_neoforge_versions(minecraft_version: str | None = None, version_type: str | None = None) -> list[str]:
    if version_type and version_type not in ["release"]:
        raise ValueError("Invalid NeoForge version type. Must be 'release' or None.")
    try:
        client = await get_http_client()
        response = await client.get("https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml")
        response.raise_for_status()
        root = ET.fromstring(response.text)
        versions_element = root.find(".//versions")
        if versions_element is None:
            return []
        versions = []
        for v_elem in versions_element.findall("version"):
            version = v_elem.text
            if version:
                if version_type == "release" and "-beta" in version:
                    continue
                versions.append(version)
        versions.reverse()
        return versions
    except (httpx.HTTPError, ET.ParseError) as e:
        raise RuntimeError(f"Error fetching/parsing NeoForge versions: {e}") from e
