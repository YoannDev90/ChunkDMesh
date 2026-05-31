import logging

from colorama import Fore, Style


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
