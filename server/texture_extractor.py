"""Extract block textures from Minecraft client jar + mod jars for rendering."""

import io
import json
import zipfile
from pathlib import Path
from typing import Optional

from PIL import Image


def _model_path(bs: dict) -> str | None:
    variants = bs.get("variants")
    if not variants:
        return None
    for vdata in variants.values():
        if isinstance(vdata, list):
            return vdata[0].get("model", "")
        elif isinstance(vdata, dict):
            return vdata.get("model", "")
    return None


def _texture_path(ref: str) -> str | None:
    """Convert a Minecraft texture ref to jar path. e.g. 'minecraft:block/stone' or 'block/stone'."""
    if ref.startswith("#"):
        return None
    if ":" in ref:
        ns, path = ref.split(":", 1)
    else:
        ns, path = "minecraft", ref
    if path.startswith("/"):
        path = path[1:]
    return f"assets/{ns}/textures/{path}.png"


class TextureAtlas:
    """Holds block→texture mappings extracted from Minecraft+mod jars."""

    def __init__(self):
        self.block_texture: dict[str, str] = {}  # block_name → jar_texture_path
        self.cache: dict[str, Image.Image] = {}
        self.jars: list[zipfile.ZipFile] = []

    def load_jar(self, jar_path: Path, skip_scan: bool = False):
        if not jar_path.exists():
            return
        zf = zipfile.ZipFile(jar_path)
        self.jars.append(zf)
        if not skip_scan:
            self._scan_jar(zf)

    def _scan_jar(self, zf: zipfile.ZipFile):
        names = set(zf.namelist())
        for name in names:
            if not name.startswith("assets/") or "/blockstates/" not in name or not name.endswith(".json"):
                continue
            mod_ns = name.split("/")[1]
            block_name = name.rsplit("/", 1)[-1].replace(".json", "")
            full_name = f"{mod_ns}:{block_name}"
            if full_name in self.block_texture:
                continue
            try:
                bs = json.loads(zf.read(name))
            except (json.JSONDecodeError, KeyError):
                continue
            model = _model_path(bs)
            if not model:
                continue
            texture = self._resolve_top_texture(zf, names, model)
            if texture:
                self.block_texture[full_name] = texture

    def _resolve_top_texture(self, zf: zipfile.ZipFile, names: set, model_path: str) -> str | None:
        if ":" in model_path:
            _, model_path = model_path.split(":", 1)
        model_path = model_path.lstrip("/")
        # Walk model parent chain
        chain = []
        current = model_path
        seen = set()
        while current and current not in seen:
            seen.add(current)
            p = f"assets/minecraft/models/{current}.json"
            if p in names:
                try:
                    model = json.loads(zf.read(p))
                except (json.JSONDecodeError, KeyError):
                    break
            else:
                # Try mod namespace
                if ":" in current:
                    ns, rest = current.split(":", 1)
                else:
                    ns, rest = "minecraft", current
                p = f"assets/{ns}/models/{rest}.json"
                try:
                    model = json.loads(zf.read(p))
                except (json.JSONDecodeError, KeyError):
                    break
            chain.append(model)
            parent = model.get("parent", "")
            if parent == "block/block":
                break
            if parent:
                if ":" in parent:
                    parent = parent.split(":", 1)[1]
                current = parent.lstrip("/")
            else:
                break

        # Collect texture variables (child first)
        tex_vars: dict[str, str] = {}
        for model in chain:
            for k, v in model.get("textures", {}).items():
                if not v.startswith("#"):
                    tex_vars[k] = v

        def _resolve(var: str) -> str | None:
            while var.startswith("#"):
                var = var[1:]
                if var in tex_vars:
                    val = tex_vars[var]
                    if not val.startswith("#"):
                        return val
                    var = val
                else:
                    return None
            return var

        priorities = ["up", "top", "all", "side", "particle", "bottom"]
        for model in chain:
            textures = model.get("textures", {})
            for key in priorities:
                if key in textures:
                    resolved = _resolve(textures[key])
                    if resolved:
                        return resolved

        for model in chain:
            for v in model.get("textures", {}).values():
                if not v.startswith("#"):
                    return v
        return None

    def get_texture(self, block_name: str) -> Image.Image | None:
        tex = self.block_texture.get(block_name)
        if not tex:
            return None
        if tex in self.cache:
            return self.cache[tex]
        for zf in self.jars:
            try:
                data = zf.read(tex)
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                self.cache[tex] = img
                return img
            except KeyError:
                continue
        return None

    def close(self):
        for zf in self.jars:
            zf.close()
        self.jars.clear()
        self.cache.clear()


def download_client_jar(mc_version: str, dest: Path) -> Path:
    """Download the Minecraft client jar for a version. Returns path to jar."""
    import httpx
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = httpx.get("https://piston-meta.mojang.com/mc/game/version_manifest.json")
    manifest = r.json()
    url = None
    for v in manifest["versions"]:
        if v["id"] == mc_version:
            vr = httpx.get(v["url"]).json()
            url = vr["downloads"]["client"]["url"]
            break
    if not url:
        raise RuntimeError(f"Version {mc_version} not found")
    r = httpx.get(url, follow_redirects=True)
    dest.write_bytes(r.content)
    return dest


CACHE_VERSION = 2


def _atlas_cache_path(client_jar_dir: Path) -> Path:
    return client_jar_dir / "atlas_cache.json"


def save_atlas_cache(atlas: TextureAtlas, client_jar_dir: Path):
    cache = {
        "version": CACHE_VERSION,
        "blocks": atlas.block_texture,
    }
    path = _atlas_cache_path(client_jar_dir)
    path.write_text(json.dumps(cache, separators=(",", ":")))


def load_atlas_cache(client_jar_dir: Path) -> dict[str, str] | None:
    path = _atlas_cache_path(client_jar_dir)
    if not path.exists():
        return None
    try:
        cache = json.loads(path.read_text())
        if cache.get("version") != CACHE_VERSION:
            return None
        return cache["blocks"]
    except (json.JSONDecodeError, KeyError):
        return None


def build_texture_atlas(
    mc_version: str,
    client_jar_dir: Path,
    mod_jars: list[Path],
) -> TextureAtlas:
    atlas = TextureAtlas()

    # Load cached mapping first (avoids re-downloading the 24MB jar)
    cached = load_atlas_cache(client_jar_dir)
    if cached:
        atlas.block_texture = dict(cached)
        # Still open jars for texture loading
        client_jar = client_jar_dir / f"client-{mc_version}.jar"
        if client_jar.exists():
            atlas.load_jar(client_jar, skip_scan=True)
        for mj in mod_jars:
            if mj.exists():
                atlas.load_jar(mj, skip_scan=True)
        return atlas

    # First time: download client jar + scan everything
    client_jar = download_client_jar(mc_version, client_jar_dir / f"client-{mc_version}.jar")
    atlas.load_jar(client_jar)
    for mod_jar in mod_jars:
        atlas.load_jar(mod_jar)

    # Cache the mapping for subsequent runs
    save_atlas_cache(atlas, client_jar_dir)
    return atlas
