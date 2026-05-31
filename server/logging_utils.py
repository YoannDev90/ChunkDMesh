import json
import logging

from colorama import Fore, Style


def load_logging_config(path="config/logging_config.json"):
    with open(path, "r") as f:
        config = json.load(f)
    return config


class ColoredFormatter(logging.Formatter):
    """Colorise les logs console selon leur niveau."""

    LEVEL_COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, "")
        levelname = record.levelname
        if color:
            record.levelname = f"{color}{levelname}{Style.RESET_ALL}"
        try:
            return super().format(record)
        finally:
            record.levelname = levelname


def setup_logging():
    logging_config = load_logging_config()
    logging.config.dictConfig(config=logging_config)
