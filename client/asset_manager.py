import hashlib
import json
import secrets
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from java_utils import ensure_java

WORK_DIR = Path.home() / ".chunkdmesh" / "work"
RCON_PASSWORD_FILE = ".rcon_password"

_LOADER_CONFIGS = {
    "fabric": {
        "install_url": "https://meta.fabricmc.net/v2/versions/loader/{mc_version}/{loader_version}/1.0.0/server/jar",
        "installer_args": [],
        "installed_jar_patterns": [
            "fabric-server-mc.{mc_version}-loader.{loader_version}-launcher.{mc_version}.jar",
        ],
    },
    "forge": {
        "install_url": "https://maven.minecraftforge.net/net/minecraftforge/forge/{mc_version}-{loader_version}/forge-{mc_version}-{loader_version}-installer.jar",
        "installer_jar": "forge-{mc_version}-{loader_version}-installer.jar",
        "installer_args": [],
        "installed_jar_patterns": [
            "forge-{mc_version}-{loader_version}.jar",
            "forge-{mc_version}-{loader_version}-universal.jar",
            "forge-{mc_version}-{loader_version}-server.jar",
        ],
    },
    "quilt": {
        "install_url": "https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-installer/{loader_version}/quilt-installer-{loader_version}.jar",
        "installer_jar": "quilt-server-installer-{loader_version}.jar",
        "installer_args": ["--install-server"],
        "installed_jar_patterns": [
            "quilt-server-{loader_version}.jar",
            "quilt-server-mc.{mc_version}-ql.{loader_version}.jar",
        ],
    },
    "neoforge": {
        "install_url": "https://maven.neoforged.net/releases/net/neoforged/neoforge/{loader_version}/neoforge-{mc_version}-{loader_version}-installer.jar",
        "installer_jar": "neoforge-{mc_version}-{loader_version}-installer.jar",
        "installer_args": ["--install-server"],
        "installed_jar_patterns": [
            "neoforge-{mc_version}-{loader_version}.jar",
            "neoforge-{mc_version}-{loader_version}-universal.jar",
        ],
    },
}


class AssetManager:
    def __init__(self, server_url: str, token: str, work_dir: Path = WORK_DIR):
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.work_dir = work_dir
        self.headers = {"Authorization": f"Bearer {token}"}

    def _get(self, path: str) -> httpx.Response:
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            resp = client.get(f"{self.server_url}{path}", headers=self.headers)
            resp.raise_for_status()
            return resp

    def download_mods(self, expected_hash: str | None = None) -> Path:
        zip_path = self.work_dir / "mods.zip"

        if zip_path.exists() and expected_hash:
            if self._verify_hash(zip_path, expected_hash):
                print("mods.zip already present and hash matches")
                return zip_path
            print("mods.zip hash mismatch, re-downloading...")

        self.work_dir.mkdir(parents=True, exist_ok=True)

        print("Downloading mods.zip...")
        with httpx.Client(follow_redirects=True, timeout=300, headers=self.headers) as client, \
                client.stream("GET", f"{self.server_url}/assets/mods.zip") as resp:
            resp.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=1024 * 64):
                    f.write(chunk)
        print(f"Downloaded to {zip_path}")

        if expected_hash:
            if not self._verify_hash(zip_path, expected_hash):
                zip_path.unlink()
                raise ValueError("Hash mismatch for mods.zip")
            print("Hash verified")

        return zip_path

    def download_config(self) -> dict:
        print("Downloading config.json...")
        resp = self._get("/assets/config.json")
        config = resp.json()

        config_path = self.work_dir / "chunky_config.json"
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        print(f"Config saved to {config_path}")

        return config

    def download_from_modrinth(
        self, project_id: str, version: str, mc_version: str, loader: str
    ) -> Path:
        import httpx

        url = f"https://api.modrinth.com/v2/project/{project_id}/version"
        params = {}
        if loader:
            params["loaders"] = f'["{loader}"]'
        if mc_version:
            params["game_versions"] = f'["{mc_version}"]'

        resp = httpx.get(url, params=params, follow_redirects=True)
        resp.raise_for_status()
        releases = resp.json()

        target = None
        for r in releases:
            if version and version in r.get("version_number", ""):
                target = r
                break
        if not target and releases:
            target = releases[0]

        if not target:
            raise RuntimeError(f"No Modrinth version found for {project_id}")

        files = target.get("files", [])
        if not files:
            raise RuntimeError(f"No files in Modrinth release for {project_id}")

        dl = files[0]
        jar_url = dl["url"]
        filename = dl["filename"]

        mods_dir = self.work_dir / "server" / "mods"
        mods_dir.mkdir(parents=True, exist_ok=True)
        dest = mods_dir / filename

        if dest.exists():
            print(f"Already downloaded: {filename}")
            return dest

        print(f"Downloading {filename} from Modrinth...")
        with httpx.stream("GET", jar_url, follow_redirects=True) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(8192):
                    f.write(chunk)

        print(f"Saved: {dest}")
        return dest

    def extract_mods(self, zip_path: Path, dest: Path | None = None) -> Path:
        mods_dir = dest or self.work_dir / "server" / "mods"
        mods_dir.mkdir(parents=True, exist_ok=True)

        print(f"Extracting mods to {mods_dir}...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                target = (mods_dir / info.filename).resolve()
                if not str(target).startswith(str(mods_dir.resolve())):
                    raise RuntimeError(f"Path traversal blocked: {info.filename}")
            zf.extractall(mods_dir)

        extracted = list(mods_dir.iterdir())
        print(f"Extracted {len(extracted)} items")
        return mods_dir

    def get_rcon_password(self) -> str:
        pw_file = self.work_dir / RCON_PASSWORD_FILE
        if pw_file.exists():
            return pw_file.read_text().strip()
        pw = secrets.token_hex(16)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        pw_file.write_text(pw)
        return pw

    def write_server_properties(self, seed=None) -> Path:
        server_dir = self.work_dir / "server"
        server_dir.mkdir(parents=True, exist_ok=True)

        rcon_password = self.get_rcon_password()

        props = {
            "level-name": "world",
            "level-seed": str(seed) if seed is not None else "0",
            "gamemode": "creative",
            "spawn-protection": "0",
            "max-tick-time": "60000",
            "generator-settings": "{}",
            "require-resource-pack": "false",
            "spawn-monsters": "false",
            "spawn-animals": "false",
            "spawn-npcs": "false",
            "view-distance": "8",
            "enable-rcon": "true",
            "rcon.port": "25575",
            "rcon.password": rcon_password,
            "broadcast-console-to-ops": "false",
            "broadcast-rcon-to-ops": "false",
            "online-mode": "false",
        }
        props_path = server_dir / "server.properties"
        with open(props_path, "w") as f:
            for k, v in props.items():
                f.write(f"{k}={v}\n")

        return props_path

    def setup_server_dir(self, mc_version: str, loader: str, loader_version: str) -> Path:
        server_dir = self.work_dir / "server"
        server_dir.mkdir(parents=True, exist_ok=True)

        eula_path = server_dir / "eula.txt"
        if not eula_path.exists():
            with open(eula_path, "w") as f:
                f.write("eula=true\n")

        return server_dir

    def get_server_jar(self, mc_version: str, loader: str, loader_version: str) -> Path:
        server_dir = self.work_dir / "server"
        server_dir.mkdir(parents=True, exist_ok=True)

        cfg = _LOADER_CONFIGS.get(loader)
        if not cfg:
            raise ValueError(f"Unsupported loader: {loader}")

        java_home = ensure_java(mc_version)
        java_bin = java_home / "bin" / "java"

        return self._install_loader(server_dir, java_bin, mc_version, loader_version, cfg)

    def _install_loader(self, server_dir: Path, java_bin: Path, mc_version: str, loader_version: str, cfg: dict) -> Path:
        args = {"mc_version": mc_version, "loader_version": loader_version}

        patterns = [p.format(**args) for p in cfg["installed_jar_patterns"]]
        for name in patterns:
            path = server_dir / name
            if path.exists():
                print(f"Already installed: {path}")
                return path

        installer_jar_template = cfg.get("installer_jar")
        if installer_jar_template:
            installer_jar = server_dir / installer_jar_template.format(**args)

            if not installer_jar.exists():
                url = cfg["install_url"].format(**args)
                print(f"Downloading installer from {url}...")
                self._download_file(url, installer_jar)

            extra_args = cfg.get("installer_args", [])
            print("Running installer...")
            cmd = [str(java_bin), "-jar", str(installer_jar)] + extra_args
            result = subprocess.run(cmd, cwd=str(server_dir), capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                print(f"Installer stdout:\n{result.stdout}")
                print(f"Installer stderr:\n{result.stderr}")
                raise RuntimeError(f"Installer failed with code {result.returncode}")
            print("Installer completed successfully")
            installer_jar.unlink(missing_ok=True)
        else:
            url = cfg["install_url"].format(**args)
            jar_name = patterns[0]
            jar_path = server_dir / jar_name
            print(f"Downloading from {url}...")
            self._download_file(url, jar_path)
            print(f"Saved: {jar_path}")
            return jar_path

        for name in patterns:
            path = server_dir / name
            if path.exists():
                return path

        for jar in server_dir.glob("*.jar"):
            if loader_version in jar.name and mc_version in jar.name and "installer" not in jar.name:
                return jar

        raise RuntimeError(f"{cfg['name']} installation failed: server jar not found")

    def _download_file(self, url: str, dest: Path):
        with httpx.Client(follow_redirects=True, timeout=300) as client, client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=1024 * 64):
                    f.write(chunk)

    @staticmethod
    def _verify_hash(file_path: Path, expected_hash: str) -> bool:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 64), b""):
                sha256.update(chunk)
        return sha256.hexdigest() == expected_hash

    def cleanup(self):
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir)
            print(f"Cleaned up {self.work_dir}")
