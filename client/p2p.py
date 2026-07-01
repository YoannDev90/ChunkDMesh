"""P2P distribution using libtorrent for mods.zip and world data.

When many clients connect simultaneously, the server generates a .torrent
file for mods.zip. Clients become seeders after downloading, reducing
server bandwidth dramatically.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

TORRENTS_DIR = Path(__file__).resolve().parent.parent / "data" / "torrents"


def _ensure_torrents_dir():
    TORRENTS_DIR.mkdir(parents=True, exist_ok=True)


def create_torrent(
    file_path: Path,
    trackers: list[str] | None = None,
    piece_size: int = 256 * 1024,
) -> Path:
    """Create a .torrent file for P2P distribution.

    Args:
        file_path: Path to file to torrent.
        trackers: List of tracker announce URLs.
        piece_size: Piece size in bytes.

    Returns: Path to created .torrent file.

    Raises: RuntimeError if libtorrent not installed.
    """
    if trackers is None:
        trackers = ["udp://tracker.opentrackr.org:1337/announce"]

    _ensure_torrents_dir()
    torrent_name = file_path.stem + ".torrent"
    torrent_path = TORRENTS_DIR / torrent_name

    try:
        import libtorrent as lt
    except ImportError as e:
        raise RuntimeError("libtorrent is required for P2P. Install with: pip install libtorrent") from e

    fs = lt.file_storage()
    lt.add_files(fs, str(file_path))

    t = lt.create_torrent(fs, piece_size)
    t.set_creator("ChunkDMesh")

    for tracker in trackers:
        t.add_tracker(tracker)

    lt.set_piece_hashes(t, str(file_path.parent))

    torrent = t.generate()
    with open(torrent_path, "wb") as f:
        f.write(lt.bencode(torrent))

    logger.info("Created torrent: %s (%d pieces)", torrent_path, t.num_pieces())
    return torrent_path


class TorrentSeeder:
    """Manages libtorrent session for seeding and downloading torrents."""

    def __init__(self, save_path: Path | None = None):
        try:
            import libtorrent as lt

            self._lt = lt
        except ImportError as e:
            raise RuntimeError("libtorrent is required for P2P") from e

        self._save_path = str(save_path or Path.home() / ".chunkdmesh" / "downloads")
        os.makedirs(self._save_path, exist_ok=True)

        self._ses = lt.session()
        self._ses.listen_on(6881, 6891)

        settings = {
            "enable_dht": True,
            "enable_lsd": True,
            "enable_natpmp": True,
            "enable_upnp": True,
        }
        self._ses.apply_settings(settings)

        self._handles: dict[str, lt.torrent_handle] = {}

    def add_torrent(self, torrent_path: Path) -> str:
        """Add a .torrent file to the session for downloading.

        Args:
            torrent_path: Path to .torrent file.

        Returns: Torrent name.
        """
        info = self._lt.torrent_info(str(torrent_path))
        params = {
            "save_path": self._save_path,
            "ti": info,
        }
        handle = self._ses.add_torrent(params)
        name = info.name()
        self._handles[name] = handle

        logger.info("Added torrent: %s", name)
        return name

    def add_magnet(self, magnet_uri: str) -> str:
        """Add a magnet URI to the session.

        Args:
            magnet_uri: Magnet link string.

        Returns: Torrent name.
        """
        params = {
            "save_path": self._save_path,
            "url": magnet_uri,
        }
        handle = self._ses.add_torrent(params)
        name = handle.name() or handle.info_hash().to_string().hex()
        self._handles[name] = handle

        logger.info("Added magnet: %s", name)
        return name

    def get_status(self, name: str) -> dict:
        """Get download status for a named torrent.

        Args:
            name: Torrent name.

        Returns: Dict with progress, rates, peers, seeds, state.
        """
        handle = self._handles.get(name)
        if not handle:
            return {"error": "torrent not found"}

        status = handle.status()
        return {
            "name": name,
            "progress": round(status.progress * 100, 1),
            "download_rate": status.download_rate,
            "upload_rate": status.upload_rate,
            "num_peers": status.num_peers,
            "num_seeds": status.num_seeds,
            "state": str(status.state),
        }

    def is_complete(self, name: str) -> bool:
        """Check if torrent download is complete and seeding.

        Args:
            name: Torrent name.

        Returns: True if seeding.
        """
        handle = self._handles.get(name)
        if not handle:
            return False
        return handle.status().is_seeding

    def wait_for_completion(self, name: str, timeout: float = 600) -> bool:
        """Block until torrent download finishes.

        Args:
            name: Torrent name.
            timeout: Max seconds to wait.

        Returns: True if completed within timeout.
        """
        import time

        start = time.time()
        while time.time() - start < timeout:
            if self.is_complete(name):
                return True
            self._ses.wait_for_alert(1000)
        return False

    def remove_torrent(self, name: str):
        """Remove a torrent from the session.

        Args:
            name: Torrent name to remove.
        """
        handle = self._handles.pop(name, None)
        if handle:
            self._ses.remove_torrent(handle)
            logger.info("Removed torrent: %s", name)

    def get_all_torrents(self) -> list[dict]:
        """Return status for all tracked torrents."""
        return [self.get_status(name) for name in self._handles]

    def shutdown(self):
        """Remove all torrents and shut down the P2P session."""
        for name in list(self._handles.keys()):
            self.remove_torrent(name)
        logger.info("P2P seeder shut down")
