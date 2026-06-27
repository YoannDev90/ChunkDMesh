import httpx
from typing import Optional

CHUNKY_MODRINTH_PROJECT_ID = "fALzjamp"
FABRIC_API_PROJECT_ID = "P7dR8mSH"

_http_client = httpx.Client(follow_redirects=True, timeout=15)


def get_modrinth_download(
    project_id: str, version: str, loader: str, minecraft_version: str
) -> Optional[dict]:
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
