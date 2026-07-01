"""Server.properties generator for Minecraft server instances.

Generates a complete server.properties file with all required settings.
Designed to overwrite any auto-generated file from MC server startup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ServerProperties:
    """Complete Minecraft server.properties configuration.

    Generates a clean file on every write — no line-by-line editing.
    """

    # World
    level_name: str = "world"
    level_seed: str = "0"
    generator_settings: str = "{}"

    # Gameplay
    gamemode: str = "creative"
    difficulty: str = "normal"
    spawn_protection: str = "0"
    spawn_monsters: str = "false"
    spawn_animals: str = "false"
    spawn_npcs: str = "false"

    # RCON
    enable_rcon: str = "true"
    rcon_port: str = "25575"
    rcon_password: str = ""

    # Network / Security
    online_mode: str = "false"
    enforce_whitelist: str = "true"
    white_list: str = "true"
    broadcast_console_to_ops: str = "false"
    broadcast_rcon_to_ops: str = "false"

    # Performance
    view_distance: str = "8"
    max_tick_time: str = "60000"
    max_players: str = "1"
    require_resource_pack: str = "false"

    # Extra overrides (raw key=value lines appended at end)
    extra: dict[str, str] = field(default_factory=dict)

    def render(self) -> str:
        """Render full server.properties content."""
        props = {
            # World
            "level-name": self.level_name,
            "level-seed": self.level_seed,
            "generator-settings": self.generator_settings,
            # Gameplay
            "gamemode": self.gamemode,
            "difficulty": self.difficulty,
            "spawn-protection": self.spawn_protection,
            "spawn-monsters": self.spawn_monsters,
            "spawn-animals": self.spawn_animals,
            "spawn-npcs": self.spawn_npcs,
            # RCON
            "enable-rcon": self.enable_rcon,
            "rcon.port": self.rcon_port,
            "rcon.password": self.rcon_password,
            # Security
            "online-mode": self.online_mode,
            "enforce-whitelist": self.enforce_whitelist,
            "white-list": self.white_list,
            "broadcast-console-to-ops": self.broadcast_console_to_ops,
            "broadcast-rcon-to-ops": self.broadcast_rcon_to_ops,
            # Performance
            "view-distance": self.view_distance,
            "max-tick-time": self.max_tick_time,
            "max-players": self.max_players,
            "require-resource-pack": self.require_resource_pack,
        }
        props.update(self.extra)
        return "".join(f"{k}={v}\n" for k, v in props.items())

    def write(self, path: Path) -> Path:
        """Write server.properties to path, overwriting any existing file.

        Args:
            path: Destination file path (e.g. server_dir / "server.properties").

        Returns: Path to written file.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render())
        return path
