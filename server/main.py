import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

from api import run_api
from db import init_db
from logging_utils import setup_logging
from tasker import fill_tasks_table

logger = logging.getLogger(__name__)


def _open_in_editor(path: Path) -> None:
    """Open the config file in the OS default text editor (best-effort)."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        subprocess.run([editor, str(path)], check=False)
        return
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", "-t", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        logger.exception("Could not open config in the default editor")


async def _ensure_config(config) -> None:
    """Guide the operator through filling the config when it's still the NaN template.

    In an interactive terminal the file is opened in the OS default text editor
    and re-validated after each save (up to 3 attempts). Headless runs just fail
    with a clear message instead of a raw traceback.
    """
    if not config.is_unconfigured():
        await config.validate()
        return

    interactive = sys.stdin is not None and sys.stdin.isatty()
    if not interactive:
        raise RuntimeError(
            f"World config is unconfigured ({config.path}). "
            "Fill minecraft_version/minecraft_loader/loader_version/chunky_version, then restart."
        )

    for attempt in range(1, 4):
        print(f"\n[ChunkDMesh] World config is not configured yet: {config.path}")
        print("[ChunkDMesh] Opening it in your default text editor...")
        _open_in_editor(Path(config.path))
        try:
            input(f"[ChunkDMesh] Attempt {attempt}/3 — press Enter once you've saved the file...")
        except EOFError:
            raise RuntimeError("No input available; cannot confirm config edit.") from None
        config.reload()
        if not config.is_unconfigured():
            await config.validate()
            return

    raise RuntimeError(f"Config still unconfigured after 3 attempts: {config.path}")


async def main() -> None:
    setup_logging()
    await init_db()
    from config import Config

    config = Config()
    try:
        await _ensure_config(config)
    except Exception as exc:
        logger.exception("Config setup failed")
        print(f"[ChunkDMesh] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    await fill_tasks_table(config)
    await run_api()


if __name__ == "__main__":
    asyncio.run(main())
