# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the ChunkDMesh client executable (onedir)."""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
CLIENT_DIR = ROOT / "client"
SERVER_DIR = ROOT / "server"

a = Analysis(
    [str(CLIENT_DIR / "main.py")],
    pathex=[str(CLIENT_DIR), str(SERVER_DIR), str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="chunkdmesh-client",
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
    name="chunkdmesh-client",
)
