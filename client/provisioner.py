"""Provisioning: login, config fetch, Java setup, loader install, mods download, mcmap binary."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
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

    # ── mcmap binary setup ───────────────────────────────────

    @staticmethod
    def _detect_rust_toolchain() -> bool:
        """Check if Rust/Cargo toolchain is installed."""
        return shutil.which("cargo") is not None and shutil.which("rustc") is not None

    @staticmethod
    def _detect_platform() -> str | None:
        """Return the Rust target triple for the current platform, or None if unsupported."""
        os_name = sys.platform
        machine = platform.machine()

        _map = {
            ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
            ("linux", "aarch64"): "aarch64-unknown-linux-gnu",
            ("linux", "armv7l"): "armv7-unknown-linux-gnueabihf",
            ("darwin", "x86_64"): "x86_64-apple-darwin",
            ("darwin", "arm64"): "aarch64-apple-darwin",
            ("win32", "AMD64"): "x86_64-pc-windows-msvc",
        }
        return _map.get((os_name, machine))

    @staticmethod
    def _platform_to_download_name(target: str) -> str:
        """Convert Rust target triple to the download name used by the server."""
        _map = {
            "x86_64-unknown-linux-gnu": "linux-amd64",
            "aarch64-unknown-linux-gnu": "linux-arm64",
            "armv7-unknown-linux-gnueabihf": "linux-armv7",
            "x86_64-apple-darwin": "macos-amd64",
            "aarch64-apple-darwin": "macos-arm64",
            "x86_64-pc-windows-msvc": "windows-amd64.exe",
        }
        return _map.get(target, target)

    def setup_mcmap(self, work_dir: Path, *, auto_compile: bool | None = None) -> Path | None:
        """Set up the mcmap binary: compile or download pre-built.

        Args:
            work_dir: Working directory for the binary.
            auto_compile: True = compile without asking, False = download without asking,
                          None = ask user interactively (use only in CLI mode).

        Returns Path to mcmap binary, or None if setup failed/skipped.
        """
        bin_dir = work_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        mcmap_path = bin_dir / "mcmap"

        if mcmap_path.exists():
            self.log("🗺️ ", "mcmap already installed")
            return mcmap_path

        has_rust = self._detect_rust_toolchain()
        target = self._detect_platform()

        # Determine whether to compile
        compile_it = False
        if has_rust:
            if auto_compile is None:
                self.log("🦀", "Rust toolchain detected")
                compile_it = self._ask_user_choice(
                    "Compile mcmap from source for optimal performance? [Y/n] ",
                    default=True,
                )
            elif auto_compile:
                self.log("🦀", "Compiling mcmap from source (auto)...")
                compile_it = True
            else:
                self.log("🦀", "Rust detected but downloading pre-built (faster)")

        if compile_it:
            return self._compile_from_source(work_dir, mcmap_path)

        if target:
            download_name = self._platform_to_download_name(target)
            self.log("📥", f"Downloading pre-compiled mcmap for {download_name}...")
            return self._download_binary(download_name, mcmap_path)

        self.log("⚠️ ", "No mcmap binary available for this platform")
        self.log("💡", "Install Rust: https://rustup.rs")
        return None

    def _ask_user_choice(self, prompt: str, default: bool = True) -> bool:
        """Ask a yes/no question. Returns True for yes."""
        try:
            answer = input(prompt).strip().lower()
            if not answer:
                return default
            return answer in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return default

    def _compile_from_source(self, work_dir: Path, mcmap_path: Path) -> Path | None:
        """Compile mcmap from source using cargo."""
        rust_dir = work_dir / "tiler"
        if not rust_dir.exists():
            # Clone or copy the tiler source
            source_dir = Path(__file__).resolve().parent.parent / "tiler"
            if source_dir.exists():
                import shutil as _shutil

                _shutil.copytree(source_dir, rust_dir, dirs_exist_ok=True)
            else:
                self.log("❌", "tiler source not found")
                return None

        self.log("🔨", "Compiling mcmap from source...")
        try:
            result = subprocess.run(
                ["cargo", "build", "--release"],
                cwd=str(rust_dir),
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                self.log("❌", f"Build failed:\n{result.stderr[-500:]}")
                return None

            built = rust_dir / "target" / "release" / "mcmap"
            if not built.exists():
                self.log("❌", "Binary not found after build")
                return None

            import shutil as _shutil

            _shutil.copy2(str(built), str(mcmap_path))
            mcmap_path.chmod(0o755)
            self.log("✅", f"mcmap compiled: {mcmap_path}")
            return mcmap_path

        except subprocess.TimeoutExpired:
            self.log("❌", "Build timed out after 600s")
            return None
        except Exception as e:
            self.log("❌", f"Build error: {e}")
            return None

    def _download_binary(self, target_name: str, dest: Path) -> Path | None:
        """Download a pre-compiled mcmap binary from the server."""
        resp = self._get(f"/assets/mcmap/{target_name}")
        if resp.status_code != 200:
            self.log("❌", f"Download failed: {resp.status_code}")
            return None

        dest.write_bytes(resp.content)
        dest.chmod(0o755)
        size = dest.stat().st_size
        self.log("✅", f"mcmap downloaded ({size:,} bytes): {dest}")
        return dest

    def _get(self, path: str) -> httpx.Response:
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            return client.get(f"{self.server_url}{path}", headers=self.auth_headers)
