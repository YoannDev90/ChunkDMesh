"""Provisioning: login, config fetch, Java setup, loader install, mods download."""

from __future__ import annotations

from pathlib import Path

import httpx


class Provisioner:
    def __init__(self, server_url: str, token: str, log_fn, measure_ctx=None):
        self.server_url = server_url
        self.token = token
        self.auth_headers = {"Authorization": f"Bearer {token}"}
        self.log = log_fn
        self._measure = measure_ctx

    def fetch_config(self) -> dict | None:
        resp = self._get("/assets/config.json")
        if resp.status_code != 200:
            self.log("❌", f"Config fetch failed: {resp.status_code} - {resp.text}")
            return None
        config = resp.json()
        mc_version = config.get("minecraft_version", "1.20.4")
        loader = config.get("minecraft_loader", "fabric")
        loader_version = config.get("loader_version", "0.19.3")
        seed = config.get("seed", 0)
        radius = config.get("radius", 1024)
        shape = config.get("shape", "square")
        dimension = config.get("dimension", "overworld")
        self.log("⚙️ ", f"MC {mc_version} / {loader} {loader_version}")
        self.log("⚙️ ", f"Seed: {seed} / Radius: {radius} / Shape: {shape} / Dim: {dimension}")
        return config

    def setup_java(self, mc_version: str):
        from java_utils import ensure_java

        java_home = ensure_java(mc_version)
        java_bin = java_home / "bin" / "java"
        self.log("☕", f"Java ready: {java_home}")
        return java_bin

    def setup_server(self, asset_mgr, mc_version: str, loader: str, loader_version: str) -> Path:
        server_dir = asset_mgr.setup_server_dir(mc_version, loader, loader_version)
        self.log("📁", f"Server dir: {server_dir}")
        return server_dir

    def download_mods(self, asset_mgr, config: dict, mc_version: str, loader: str):
        if config.get("has_mods_zip"):
            mods_zip = asset_mgr.download_mods()
            self.log("📥", f"Mods downloaded: {mods_zip}")
            self.log("🧩", "Extracting mods...")
            asset_mgr.extract_mods(mods_zip)
            self.log("🧩", "Mods extracted")
        else:
            self.log("📥", "Downloading Chunky + deps from Modrinth...")
            from modrinth import CHUNKY_MODRINTH_PROJECT_ID, FABRIC_API_PROJECT_ID, get_modrinth_download

            chunky_ver = config.get("chunky_version", "")
            chunky_info = get_modrinth_download(CHUNKY_MODRINTH_PROJECT_ID, chunky_ver, loader, mc_version)
            if not chunky_info:
                self.log("❌", "Could not find Chunky version on Modrinth")
                return False
            asset_mgr.download_from_modrinth(CHUNKY_MODRINTH_PROJECT_ID, chunky_ver, mc_version, loader)
            fabric_api_info = get_modrinth_download(FABRIC_API_PROJECT_ID, "", "fabric", mc_version)
            if fabric_api_info:
                asset_mgr.download_from_modrinth(FABRIC_API_PROJECT_ID, "", mc_version, "fabric")
                self.log("📥", "Fabric API downloaded")
            else:
                self.log("⚠️", "Fabric API not found, continuing without it")
        return True

    def install_loader(self, asset_mgr, mc_version: str, loader: str, loader_version: str) -> Path | None:
        jar_path = asset_mgr.get_server_jar(mc_version, loader, loader_version)
        self.log("🔧", f"Server jar: {jar_path}")
        return jar_path

    def download_palettes(self, work_dir: Path) -> bool:
        """Download palette files from server for local mcmap rendering."""
        data_dir = work_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        palettes = ["block_colors.json", "biome_colors.json", "biome_tint_blocks.json"]
        downloaded = 0
        for name in palettes:
            dest = data_dir / name
            if dest.exists():
                downloaded += 1
                continue
            resp = self._get(f"/tiles/palette/{name}")
            if resp.status_code == 200:
                dest.write_bytes(resp.content)
                downloaded += 1
                self.log("🎨", f"Downloaded palette: {name}")
            else:
                self.log("⚠️", f"Palette {name} not available on server")
        return downloaded > 0

    def _get(self, path: str) -> httpx.Response:
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            return client.get(f"{self.server_url}{path}", headers=self.auth_headers)
