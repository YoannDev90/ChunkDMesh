# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the ChunkDMesh server executable (onedir)."""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
SERVER_DIR = ROOT / "server"

_uvicorn_standard = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.loops.uvloop",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "aiosqlite",
]

binaries = []
rust_release = ROOT / "tiler" / "target" / "release"
rust_name = "mcmap.exe" if sys.platform == "win32" else "mcmap"
rust_binary = rust_release / rust_name
if rust_binary.exists():
    binaries.append((str(rust_binary), "tiler/target/release"))
else:
    print(f"WARNING: Rust mcmap binary not found at {rust_binary}; tiles route will be degraded.")

datas = [
    (str(SERVER_DIR / "templates"), "templates"),
    (str(SERVER_DIR / "config" / "favicon.ico"), "config"),
    (str(SERVER_DIR / "config" / "logging_config.json5"), "config"),
    (str(SERVER_DIR / "config" / "world_config.json5"), "data"),
]

a = Analysis(
    [str(SERVER_DIR / "main.py")],
    pathex=[str(SERVER_DIR), str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=_uvicorn_standard,
    hookspath=[],
    runtime_hooks=[str(ROOT / "packaging" / "server_runtime_hook.py")],
    excludes=["watchfiles"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="chunkdmesh-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="chunkdmesh-server",
)
