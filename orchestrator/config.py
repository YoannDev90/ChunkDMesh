import json5
import json
from pathlib import Path

LOGGER_NAME = "CHUNKDMESH"

ASCII_ART = r"""

                                                                                                         
   _|_|_|  _|    _|  _|    _|  _|      _|  _|    _|  _|_|_|    _|      _|  _|_|_|_|    _|_|_|  _|    _|  
 _|        _|    _|  _|    _|  _|_|    _|  _|  _|    _|    _|  _|_|  _|_|  _|        _|        _|    _|  
 _|        _|_|_|_|  _|    _|  _|  _|  _|  _|_|      _|    _|  _|  _|  _|  _|_|_|      _|_|    _|_|_|_|  
 _|        _|    _|  _|    _|  _|    _|_|  _|  _|    _|    _|  _|      _|  _|              _|  _|    _|  
   _|_|_|  _|    _|    _|_|    _|      _|  _|    _|  _|_|_|    _|      _|  _|_|_|_|  _|_|_|    _|    _|  
                                                                                                         

"""

CONFIG_PATH = Path("config/world_config.json5")
LOGGING_CONFIG_PATH = Path("config/logging_config.json")


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    """Charge la configuration du monde à partir d'un fichier JSON5."""
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
