import json
from pathlib import Path
from typing import List, Union, Optional
from pydantic import BaseModel, Field
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

CONFIG_PATH = Path(__file__).parent / "config/world_config.json5"
LOGGING_CONFIG_PATH = Path(__file__).parent / "config/logging_config.json"
DB_PATH = Path(__file__).parent / "data/chunkdmesh.db"
ACTIVE_CONFIG_PATH = Path(__file__).parent / "data/world_settings.json"

HOST = "0.0.0.0"
PORT = 5000


class WorldConfig(BaseModel):
    world_name: str = "NewWorld"
    center: Union[str, List[int]] = "spawn"
    seed: Optional[int] = None
    radius: int = 1000
    shape: str = "square"
    pattern: str = "region"
    max_clients: int = 8
    chunk_format: str = "sha256"
    verification: bool = True
    batch_size: int = 50


def load_config(config_path: Path = CONFIG_PATH) -> WorldConfig:
    """Charge la configuration du monde et la valide via Pydantic."""
    data = {}

    # Priorité à data/world_settings.json
    if config_path == CONFIG_PATH and ACTIVE_CONFIG_PATH.exists():
        with ACTIVE_CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    elif config_path.is_file():
        with config_path.open("r", encoding="utf-8") as f:
            data = json5.load(f)

    # Nettoyage des NaN pour Pydantic
    if "seed" in data and (data["seed"] is None or str(data["seed"]) == "nan"):
        data["seed"] = None
    if "center" in data and isinstance(data["center"], list):
        if any(str(x) == "nan" for x in data["center"]):
            data["center"] = "spawn"

    return WorldConfig(**data)


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
