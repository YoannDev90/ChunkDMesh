#!/usr/bin/env python3
"""Generate block/biome color palette from Minecraft client jar.

Extracts textures, parses block models (prefers 'top' texture),
detects biome-tinted blocks (tintindex in models), extracts biome
colors from biome definition files and colormap PNGs.

Output (in data/):
  block_colors.json     — block_name → {r,g,b}
  biome_colors.json     — biome_name → {r,g,b}
  biome_tint_blocks.json  — [block_name, ...]

Usage:
  python generate_block_palette.py                          # auto-download 1.20.4
  python generate_block_palette.py --version 1.21           # any version
  python generate_block_palette.py --jar path/to/jar        # from existing jar
"""

import argparse
import json
import sys
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow required: pip install pillow", file=sys.stderr)
    sys.exit(1)

VERSION_MANIFEST_URL = "https://launchermeta.mojang.com/mc/game/version_manifest.json"


# ── helpers ──────────────────────────────────────────────────────────


def get_jar_url(version: str) -> str | None:
    try:
        with urllib.request.urlopen(VERSION_MANIFEST_URL, timeout=10) as r:
            manifest = json.loads(r.read())
        for v in manifest.get("versions", []):
            if v["id"] == version:
                with urllib.request.urlopen(v["url"], timeout=10) as r2:
                    return json.loads(r2.read())["downloads"]["client"]["url"]
    except Exception as e:
        print(f"Warning: manifest lookup failed ({e})", file=sys.stderr)
    return None


def download_jar(version: str) -> bytes | None:
    url = get_jar_url(version)
    if not url:
        return None
    print(f"Downloading {version} client jar...", file=sys.stderr)
    try:
        with urllib.request.urlopen(url, timeout=180) as r:
            return r.read()
    except Exception as e:
        print(f"Download failed: {e}", file=sys.stderr)
    return None


def dominant_color(img: Image.Image) -> tuple[int, int, int]:
    """Dominant color: average of non-transparent pixels, center-weighted."""
    img = img.convert("RGBA")
    pixels = list(img.getdata())
    valid = [(r, g, b) for r, g, b, a in pixels if a > 128]
    if not valid:
        return (140, 100, 80)
    n = len(valid)
    mid = n // 2
    r = sum(p[0] for p in valid) + sum(valid[mid][0] for _ in range(n))
    g = sum(p[1] for p in valid) + sum(valid[mid][1] for _ in range(n))
    b = sum(p[2] for p in valid) + sum(valid[mid][2] for _ in range(n))
    return (r // (n * 2), g // (n * 2), b // (n * 2))


# ── block model parsing ──────────────────────────────────────────────


def walk_model_textures(jar: zipfile.ZipFile, model_rel: str, visited: set | None = None) -> list[str]:
    """Walk block model parent chain, return ordered texture paths (top-preferred)."""
    if visited is None:
        visited = set()
    if model_rel in visited:
        return []
    visited.add(model_rel)

    model_path = f"assets/minecraft/models/{model_rel}"
    try:
        with jar.open(model_path) as f:
            model = json.loads(f.read())
    except (KeyError, json.JSONDecodeError):
        return []

    textures = model.get("textures", {})
    tex_paths: list[str] = []

    # Priority order: "top" > "all" > "cross" > "particle" > everything else
    priority = ["top", "all", "cross", "texture", "particle", "side", "end", "front", "0", "1"]
    seen_keys = set()
    for key in priority:
        val = textures.get(key)
        if val and isinstance(val, str) and not val.startswith("#"):
            tex_paths.append(val)
            seen_keys.add(key)
    for key, val in textures.items():
        if key not in seen_keys and isinstance(val, str) and not val.startswith("#"):
            tex_paths.append(val)

    resolved = [f"assets/minecraft/textures/{t}.png" for t in tex_paths]

    # Walk parent
    parent = model.get("parent")
    if parent:
        pp = parent if parent.endswith(".json") else f"{parent}.json"
        resolved.extend(walk_model_textures(jar, pp, visited))

    return resolved


def _resolve_model_name(model_val: str) -> str:
    """Convert 'minecraft:block/grass_block' to 'block/grass_block.json'."""
    m = model_val.removeprefix("minecraft:")
    if not m.endswith(".json"):
        m += ".json"
    return m


def has_tintindex(jar: zipfile.ZipFile, model_rel: str, visited: set | None = None) -> bool:
    """Check if any face in the block model has tintindex (grass/foliage biome tint)."""
    if visited is None:
        visited = set()
    if model_rel in visited:
        return False
    visited.add(model_rel)

    model_path = f"assets/minecraft/models/{model_rel}"
    try:
        with jar.open(model_path) as f:
            model = json.loads(f.read())
    except (KeyError, json.JSONDecodeError):
        return False

    for elem in model.get("elements", []):
        faces = elem.get("faces", {})
        for face_data in faces.values():
            if "tintindex" in face_data:
                return True

    parent = model.get("parent")
    if parent:
        pp = _resolve_model_name(parent)
        if has_tintindex(jar, pp, visited):
            return True

    # Check variants (e.g. facing=north → different model)
    for variant in model.get("variants", {}).values():
        if isinstance(variant, list):
            for v in variant:
                if isinstance(v, dict) and "model" in v:
                    mp = _resolve_model_name(v["model"])
                    if has_tintindex(jar, mp, visited):
                        return True
        elif isinstance(variant, dict) and "model" in variant:
            mp = _resolve_model_name(variant["model"])
            if has_tintindex(jar, mp, visited):
                return True

    return False


# ── biome data extraction ────────────────────────────────────────────


def extract_biome_colors(
    jar: zipfile.ZipFile,
) -> dict[str, dict]:
    """Extract biome overlay colors from jar biome data + colormap.

    Priority:
      1. explicit `effects.grass_color` / `effects.foliage_color` in biome JSON
      2. sampled from colormap PNG (grass.png / foliage.png) using temperature+downfall
      3. fallback: derive from temperature/downfall heuristically
    """
    biomes: dict[str, dict] = {}
    colormaps: dict[str, Image.Image] = {}

    # Load colormap textures
    for cmap_name in ("grass", "foliage"):
        path = f"assets/minecraft/textures/colormap/{cmap_name}.png"
        try:
            with jar.open(path) as f:
                colormaps[cmap_name] = Image.open(f).convert("RGBA")
        except KeyError:
            pass

    def sample_colormap(cmap: str, temperature: float, downfall: float) -> tuple:
        """Sample colormap at temperature×downfall coordinates."""
        if cmap not in colormaps:
            return (140, 190, 100)
        img = colormaps[cmap]
        w, h = img.size
        tx = int((1.0 - temperature) * (w - 1))
        ty = int((1.0 - downfall) * (h - 1))
        tx = max(0, min(w - 1, tx))
        ty = max(0, min(h - 1, ty))
        px = img.getpixel((tx, ty))
        return (px[0], px[1], px[2])

    # Find biome JSON files in the jar's data pack (1.18+)
    biome_prefix = "data/minecraft/worldgen/biome/"
    for name in jar.namelist():
        if name.startswith(biome_prefix) and name.endswith(".json"):
            try:
                with jar.open(name) as f:
                    biome_data = json.loads(f.read())
            except (json.JSONDecodeError, KeyError):
                continue

            biome_name = name.removeprefix(biome_prefix).removesuffix(".json")
            if not biome_name.startswith("minecraft:"):
                biome_name = f"minecraft:{biome_name}"

            effects = biome_data.get("effects", {})
            temp = biome_data.get("temperature", 0.5)
            downfall = biome_data.get("downfall", 0.5)

            # Grass color: explicit or from colormap
            grass_color = effects.get("grass_color")
            if not grass_color:
                grass_color = sample_colormap("grass", temp, downfall)
            else:
                grass_color = (
                    (grass_color >> 16) & 0xFF,
                    (grass_color >> 8) & 0xFF,
                    grass_color & 0xFF,
                )

            # Foliage color: explicit or from colormap
            foliage_color = effects.get("foliage_color")
            if not foliage_color:
                foliage_color = sample_colormap("foliage", temp, downfall)
            else:
                foliage_color = (
                    (foliage_color >> 16) & 0xFF,
                    (foliage_color >> 8) & 0xFF,
                    foliage_color & 0xFF,
                )

            biomes[biome_name] = {
                "grass_color": {"r": grass_color[0], "g": grass_color[1], "b": grass_color[2]},
                "foliage_color": {"r": foliage_color[0], "g": foliage_color[1], "b": foliage_color[2]},
                "temperature": temp,
                "downfall": downfall,
            }

    return biomes


# ── main pipeline ────────────────────────────────────────────────────


def build_palette_from_jar(jar_data: bytes) -> tuple[dict, dict, list[str]]:
    """Extract block colors, biome colors, and tint block list from jar.

    Returns:
      (block_palette, biome_palette, biome_tint_blocks)
    """
    block_palette: dict[str, dict] = {}
    tex_cache: dict[str, tuple] = {}
    model_cache: dict[str, list[str]] = {}
    tint_check_cache: dict[str, bool] = {}

    with zipfile.ZipFile(BytesIO(jar_data)) as jar:
        # Phase 1: cache all block textures
        for name in jar.namelist():
            if "/textures/block/" not in name or not name.endswith(".png"):
                continue
            # Support both "textures/block/" and "textures/blocks/"
            try:
                with jar.open(name) as f:
                    img = Image.open(f)
                    tex_cache[name] = dominant_color(img)
            except Exception:
                pass
        print(f"  Cached {len(tex_cache)} textures", file=sys.stderr)

        # Phase 2: resolve model → texture(s), detect tint
        for name in jar.namelist():
            if "/models/block/" not in name or not name.endswith(".json"):
                continue
            model_rel = name.removeprefix("assets/minecraft/models/")
            tex_paths = walk_model_textures(jar, model_rel)
            if tex_paths:
                model_cache[model_rel] = tex_paths
            try:
                tint_check_cache[model_rel] = has_tintindex(jar, model_rel)
            except RecursionError:
                tint_check_cache[model_rel] = False

        print(
            f"  Parsed {len(model_cache)} models, checked {sum(1 for v in tint_check_cache.values() if v)} tinted",
            file=sys.stderr,
        )

        # Phase 3: collect all known block names from blockstate files
        blockstate_prefix = "assets/minecraft/blockstates/"
        known_blocks: set[str] = set()
        for name in jar.namelist():
            if name.startswith(blockstate_prefix) and name.endswith(".json"):
                block_name = name.removeprefix(blockstate_prefix).removesuffix(".json")
                known_blocks.add(f"minecraft:{block_name}")

        print(f"  Known blocks from blockstates: {len(known_blocks)}", file=sys.stderr)

        def _resolve_default_model(bs: dict) -> str | None:
            """Get the default model from a blockstate definition."""
            variants = bs.get("variants", {})
            if variants:
                # Try the default variant (snowy=false, normal, or first entry)
                for var_name in ["", "normal", "facing=north", "axis=y"]:
                    if var_name in variants:
                        var = variants[var_name]
                        break
                else:
                    var = next(iter(variants.values()))

                if isinstance(var, list) and var:
                    var = var[0]
                if isinstance(var, dict):
                    return var.get("model", "")
                return None

            multipart = bs.get("multipart", [])
            if multipart:
                first = multipart[0]
                apply = first.get("apply", {})
                if isinstance(apply, list) and apply:
                    apply = apply[0]
                if isinstance(apply, dict):
                    return apply.get("model", "")
                return None

            return None

        def _color_from_model(model_rel: str) -> dict | None:
            if model_rel not in model_cache:
                return None
            for tex_path in model_cache[model_rel]:
                if tex_path in tex_cache:
                    c = tex_cache[tex_path]
                    return {"r": c[0], "g": c[1], "b": c[2]}
                alt = tex_path.replace("textures/block/", "textures/blocks/")
                if alt in tex_cache:
                    c = tex_cache[alt]
                    return {"r": c[0], "g": c[1], "b": c[2]}
            return None

        # Phase 4: assign color to each block (via blockstate → model → top texture)
        for block_name in sorted(known_blocks):
            short = block_name.removeprefix("minecraft:")
            bs_name = f"assets/minecraft/blockstates/{short}.json"
            try:
                with jar.open(bs_name) as f:
                    bs = json.loads(f.read())
            except Exception:
                continue

            model_id = _resolve_default_model(bs)
            color = None
            if model_id:
                model_rel = _resolve_model_name(model_id)
                color = _color_from_model(model_rel)

            # Fallback: direct model match
            if color is None:
                model_rel = f"block/{short}.json"
                color = _color_from_model(model_rel)

            # Fallback: texture match
            if color is None:
                for stem in [short, f"{short}_top"]:
                    for prefix in ["textures/block/", "textures/blocks/"]:
                        tex = f"assets/minecraft/{prefix}{stem}.png"
                        if tex in tex_cache:
                            c = tex_cache[tex]
                            color = {"r": c[0], "g": c[1], "b": c[2]}
                            break
                    if color:
                        break

            if color:
                block_palette[block_name] = color

        # Phase 5: add blocks that have a model but no blockstate (rare)
        for name in jar.namelist():
            if not name.startswith("assets/minecraft/models/block/") or not name.endswith(".json"):
                continue
            short = name.removeprefix("assets/minecraft/models/block/").removesuffix(".json")
            block_name = f"minecraft:{short}"
            if block_name in block_palette:
                continue
            # Check if there's no blockstate file for this
            bs_name = f"assets/minecraft/blockstates/{short}.json"
            if f"assets/minecraft/blockstates/{short}.json" in jar.namelist():
                continue  # has blockstate, already processed
            model_rel = f"block/{short}.json"
            if model_rel not in model_cache:
                continue
            for tex_path in model_cache[model_rel]:
                if tex_path in tex_cache:
                    c = tex_cache[tex_path]
                    block_palette[block_name] = {"r": c[0], "g": c[1], "b": c[2]}
                    break

        # Phase 6: detect biome-tinted blocks
        biome_tint_blocks: list[str] = []
        for block_name in block_palette:
            short = block_name.removeprefix("minecraft:")
            model_rel = f"block/{short}.json"
            tinted = tint_check_cache.get(model_rel, False)
            if not tinted:
                # Also check blockstate variants
                bs_name = f"assets/minecraft/blockstates/{short}.json"
                try:
                    with jar.open(bs_name) as f:
                        bs = json.loads(f.read())
                except Exception:
                    continue
                for variant in bs.get("variants", {}).values():
                    if isinstance(variant, list):
                        for v in variant:
                            if isinstance(v, dict) and "model" in v:
                                mp = _resolve_model_name(v["model"])
                                if tint_check_cache.get(mp, False):
                                    tinted = True
                                    break
                    elif isinstance(variant, dict) and "model" in variant:
                        mp = _resolve_model_name(variant["model"])
                        if tint_check_cache.get(mp, False):
                            tinted = True
                            break
            if tinted:
                biome_tint_blocks.append(block_name)

        # Phase 7: extract biome colors
        biome_palette = extract_biome_colors(jar)

    print(f"  Block palette: {len(block_palette)} entries", file=sys.stderr)
    print(f"  Biome tint blocks: {len(biome_tint_blocks)}", file=sys.stderr)
    print(f"  Biome palette: {len(biome_palette)} biomes", file=sys.stderr)

    return block_palette, biome_palette, biome_tint_blocks


def build_palette_from_assets(assets_dir: Path) -> tuple[dict, dict, list[str]]:
    """Simplified palette from assets directory (no model parsing, no biomes)."""
    tex_dir = assets_dir / "textures" / "block"
    if not tex_dir.exists():
        tex_dir = assets_dir / "textures" / "blocks"
    if not tex_dir.exists():
        print(f"Textures not found in {assets_dir}", file=sys.stderr)
        return {}, {}, []

    block_palette: dict[str, dict] = {}
    for tex_file in sorted(tex_dir.glob("*.png")):
        try:
            img = Image.open(tex_file)
            c = dominant_color(img)
            name = f"minecraft:{tex_file.stem}"
            block_palette[name] = {"r": c[0], "g": c[1], "b": c[2]}
        except Exception:
            pass

    return block_palette, {}, []


def main():
    parser = argparse.ArgumentParser(description="Generate block/biome palette from Minecraft jar")
    parser.add_argument("--jar", help="Path to Minecraft client jar")
    parser.add_argument("--assets", help="Path to extracted assets directory")
    parser.add_argument("--version", default="1.20.4", help="Minecraft version")
    parser.add_argument("--output-dir", default=None, help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else (Path(__file__).resolve().parent.parent / "data")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.assets:
        print(f"Building from assets: {args.assets}...", file=sys.stderr)
        block_palette, biome_palette, biome_tint_blocks = build_palette_from_assets(Path(args.assets))
    elif args.jar:
        print(f"Building from jar: {args.jar}...", file=sys.stderr)
        with open(args.jar, "rb") as f:
            block_palette, biome_palette, biome_tint_blocks = build_palette_from_jar(f.read())
    else:
        print(f"Downloading Minecraft {args.version}...", file=sys.stderr)
        jar_data = download_jar(args.version)
        if not jar_data:
            print("Download failed.", file=sys.stderr)
            sys.exit(1)
        block_palette, biome_palette, biome_tint_blocks = build_palette_from_jar(jar_data)

    # Write block colors
    block_path = out_dir / "block_colors.json"
    block_path.write_text(json.dumps(block_palette, indent=2))
    print(f"Wrote {block_path} ({block_path.stat().st_size / 1024:.0f} KB)", file=sys.stderr)

    # Write biome colors
    biome_path = out_dir / "biome_colors.json"
    biome_path.write_text(json.dumps(biome_palette, indent=2))
    print(f"Wrote {biome_path} ({biome_path.stat().st_size / 1024:.0f} KB)", file=sys.stderr)

    # Write tint block list
    tint_path = out_dir / "biome_tint_blocks.json"
    tint_path.write_text(json.dumps(biome_tint_blocks, indent=2))
    print(f"Wrote {tint_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
