import json
from pathlib import Path

import json5

LOGGER_NAME = "CHUNKDMESH"

ASCII_ART = r"""
 _____  _   _ _   _ _   _  _   __     ______       ___  ___ _____ _____ _   _ 
/  __ \| | | | | | | \ | || | / /     |  _  \      |  \/  ||  ___/  ___| | | |
| /  \/| |_| | | | |  \| || |/ /______| | | |______| .  . || |__ \ `--.| |_| |
| |    |  _  | | | | . ` ||    \______| | | |______| |\/| ||  __| `--. \  _  |
| \__/\| | | | |_| | |\  || |\  \     | |/ /       | |  | || |___/\__/ / | | |
 \____/\_| |_/\___/\_| \_/\_| \_/     |___/        \_|  |_/\____/\____/\_| |_/

"""

CONFIG_PATH = Path("config/world_config.json5")
LOGGING_CONFIG_PATH = Path("config/logging_config.json")
DB_PATH = Path("data/chunkdmesh.db")
ACTIVE_CONFIG_PATH = Path("data/world_settings.json")


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    """Charge la configuration du monde (priorité à data/world_settings.json)."""
    # Si on ne spécifie pas de chemin, on essaie de charger la config active d'abord
    if config_path == CONFIG_PATH and ACTIVE_CONFIG_PATH.exists():
        with ACTIVE_CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)

    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        return json5.load(f)


def load_logging_config(logging_config_path: Path = LOGGING_CONFIG_PATH) -> dict:
    """Charge la configuration de journalisation à partir d'un fichier JSON."""
    if not logging_config_path.is_file():
        raise FileNotFoundError(
            f"Logging configuration file not found: {logging_config_path}"
        )
    with logging_config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


LOGGING_CONFIG = load_logging_config()
WORLD_GEN_CONFIG = load_config()
