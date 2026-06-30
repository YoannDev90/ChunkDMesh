"""Server-side torrent file creation for mods.zip distribution."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

TORRENTS_DIR = Path(__file__).resolve().parent.parent / "data" / "torrents"


def _ensure_dir():
    TORRENTS_DIR.mkdir(parents=True, exist_ok=True)


def _hash_file(path: Path, piece_size: int = 256 * 1024) -> bytes:
    pieces = b""
    with open(path, "rb") as f:
        while True:
            data = f.read(piece_size)
            if not data:
                break
            pieces += hashlib.sha1(data).digest()
    return pieces


def _encode_bytes(data: bytes) -> bytes:
    return str(len(data)).encode() + b":" + data


def _encode_int(n: int) -> bytes:
    return b"i" + str(n).encode() + b"e"


def _encode_string(s: str) -> bytes:
    return _encode_bytes(s.encode())


def _encode_list(items: list) -> bytes:
    result = b"l"
    for item in items:
        if isinstance(item, bytes):
            result += item
        elif isinstance(item, int):
            result += _encode_int(item)
        elif isinstance(item, str):
            result += _encode_string(item)
        elif isinstance(item, list):
            result += _encode_list(item)
        elif isinstance(item, dict):
            result += _encode_dict(item)
    result += b"e"
    return result


def _encode_dict(d: dict) -> bytes:
    result = b"d"
    for key, value in d.items():
        if isinstance(key, str):
            result += _encode_string(key)
        elif isinstance(key, bytes):
            result += _encode_bytes(key)
        if isinstance(value, bytes):
            result += value
        elif isinstance(value, int):
            result += _encode_int(value)
        elif isinstance(value, str):
            result += _encode_string(value)
        elif isinstance(value, list):
            result += _encode_list(value)
        elif isinstance(value, dict):
            result += _encode_dict(value)
    result += b"e"
    return result


def create_torrent(
    file_path: Path,
    trackers: list[str] | None = None,
    piece_size: int = 256 * 1024,
) -> Path:
    if trackers is None:
        trackers = ["udp://tracker.opentrackr.org:1337/announce"]

    _ensure_dir()

    file_size = file_path.stat().st_size
    pieces = _hash_file(file_path, piece_size)

    info = {
        "name": file_path.name,
        "piece length": piece_size,
        "length": file_size,
        "pieces": pieces,
    }

    torrent = {
        "announce": trackers[0],
        "announce-list": [trackers],
        "created by": "ChunkDMesh",
        "creation date": int(time.time()),
        "info": info,
    }

    torrent_path = TORRENTS_DIR / (file_path.stem + ".torrent")
    with open(torrent_path, "wb") as f:
        f.write(_encode_dict(torrent))

    return torrent_path
