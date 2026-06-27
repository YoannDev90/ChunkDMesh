import datetime
import logging
import logging.config
from pathlib import Path

import json5
from colorama import Fore, Style


class ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }

    def formatTime(self, record, datefmt=None):
        dt = datetime.datetime.fromtimestamp(record.created)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, "")
        levelname = record.levelname
        if color:
            record.levelname = f"{color}{levelname}{Style.RESET_ALL}"
        try:
            return super().format(record)
        finally:
            record.levelname = levelname


_BASE_DIR = Path(__file__).resolve().parent


def load_logging_config(path=None):
    if path is None:
        path = str(_BASE_DIR / "config" / "logging_config.json5")
    with open(path, "r") as f:
        config = json5.load(f)
    return config.get("logging_lib_config")


def setup_logging():
    logging.ColoredFormatter = ColoredFormatter
    logging_config = load_logging_config()
    logging.config.dictConfig(config=logging_config)
    return logging.getLogger(__name__)
