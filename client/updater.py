"""Client auto-update system.

Checks the server for a newer version of the client and updates itself.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx

VERSION_FILE = Path(__file__).resolve().parent / ".version"
UPDATE_CACHE_DIR = Path.home() / ".chunkdmesh" / "updates"
CLIENT_VERSION = "0.1.0"


def get_current_version() -> str:
    """Read current client version from .version file or fallback constant.

    Returns: Version string.
    """
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    return CLIENT_VERSION


def check_update(server_url: str, token: str) -> dict | None:
    """Check server for a newer client version.

    Args:
        server_url: Server base URL.
        token: Auth token.

    Returns: Version info dict, or None on failure.
    """
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(follow_redirects=True, timeout=10) as client:
            resp = client.get(
                f"{server_url}/client/version",
                headers=headers,
            )
            if resp.status_code != 200:
                return None
            return resp.json()
    except Exception:
        return None


def download_update(server_url: str, token: str, version: str) -> Path:
    """Download client update archive from server.

    Args:
        server_url: Server base URL.
        token: Auth token.
        version: Version string for filename.

    Returns: Path to downloaded archive.
    """
    headers = {"Authorization": f"Bearer {token}"}
    UPDATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    archive_path = UPDATE_CACHE_DIR / f"client_{version}.tar.gz"

    print(f"Downloading update v{version}...")
    with (
        httpx.Client(follow_redirects=True, timeout=120, headers=headers) as client,
        client.stream("GET", f"{server_url}/client/download") as resp,
    ):
        resp.raise_for_status()
        with open(archive_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=1024 * 64):
                f.write(chunk)

    return archive_path


def apply_update(archive_path: Path):
    """Extract update archive and replace current client files.

    Creates backup before applying, rolls back on failure.

    Args:
        archive_path: Path to update tar.gz archive.

    Raises: tarfile.ExtractError on path traversal; re-raises on failure after rollback.
    """
    import tarfile

    client_dir = Path(__file__).resolve().parent
    backup_dir = client_dir.parent / "client_backup"

    print("Backing up current client...")
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    shutil.copytree(client_dir, backup_dir)

    print("Applying update...")
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise tarfile.ExtractError(f"Path traversal blocked: {member.name}")
            if hasattr(tarfile, "data_filter"):
                tar.extractall(client_dir.parent, filter="data")
            else:
                tar.extractall(client_dir.parent)

        VERSION_FILE.write_text(archive_path.stem.split("_")[1])
        print("Update applied successfully!")
    except Exception as e:
        print(f"Update failed: {e}")
        print("Rolling back...")
        if backup_dir.exists():
            shutil.rmtree(client_dir)
            shutil.move(backup_dir, client_dir)
        raise


def check_and_update(server_url: str, token: str) -> bool:
    """Full update flow: check, download, apply.

    Args:
        server_url: Server base URL.
        token: Auth token.

    Returns: True if update was applied.
    """
    current = get_current_version()
    print(f"Current client version: {current}")

    remote = check_update(server_url, token)
    if not remote:
        print("Could not check for updates")
        return False

    remote_version = remote.get("version")
    if not remote_version or remote_version == current:
        print("Client is up to date")
        return False

    print(f"Update available: {remote_version}")
    archive_path = download_update(server_url, token, remote_version)
    apply_update(archive_path)
    return True
