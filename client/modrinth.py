import atexit

import httpx

CHUNKY_MODRINTH_PROJECT_ID = "fALzjamp"
FABRIC_API_PROJECT_ID = "P7dR8mSH"

_http_client = httpx.Client(follow_redirects=True, timeout=15)
atexit.register(_http_client.close)


def get_modrinth_download(project_id: str, version: str, loader: str, minecraft_version: str) -> dict | None:
    """Fetch download info for a Modrinth project matching version/loader/MC.

    Args:
        project_id: Modrinth project ID.
        version: Specific version string (or empty for latest).
        loader: Mod loader name (fabric, forge, etc.).
        minecraft_version: Minecraft version string.

    Returns: Dict with url, filename, size, or None if not found.
    """
    url = f"https://api.modrinth.com/v2/project/{project_id}/version"
    params = {}
    if loader:
        params["loaders"] = f'["{loader}"]'
    if minecraft_version:
        params["game_versions"] = f'["{minecraft_version}"]'

    try:
        resp = _http_client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

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
