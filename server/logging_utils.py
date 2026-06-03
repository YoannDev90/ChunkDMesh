import logging
import logging.config
from typing import Optional

import json5
from colorama import Fore, Style

_current_locale = "en"
_translations = {}


class ColoredFormatter(logging.Formatter):
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


logging.ColoredFormatter = ColoredFormatter


def load_logging_config(path="server/config/logging_config.json5"):
    with open(path, "r") as f:
        config = json5.load(f)
    lib_config = config.get("logging_lib_config")
    locale_config = config.get("global_logging_config", {})
    return lib_config, locale_config


def load_translations(path="server/config/locales"):
    global _translations
    import os

    for lang_file in os.listdir(path):
        if lang_file.endswith(".json5"):
            lang = lang_file.replace(".json5", "")
            with open(f"{path}/{lang_file}") as f:
                _translations[lang] = json5.load(f).get(lang, {})

    return _translations


def set_locale(lang: str):
    global _current_locale
    if lang in _translations:
        _current_locale = lang
    else:
        print(
            f"⚠️  Language '{lang}' not found. Available: {list(_translations.keys())}"
        )


def get_message(key: str, **kwargs) -> str:
    message = _translations.get(_current_locale, {}).get(key, key)

    if kwargs:
        try:
            message = message.format(**kwargs)
        except KeyError as e:
            print(f"⚠️  Missing parameter {e} for key '{key}'")

    return message


def setup_logging():
    load_translations()
    logging_config, locale_config = load_logging_config()
    set_locale(locale_config.get("logs_locale_lang", "en"))
    logging.config.dictConfig(config=logging_config)
    return logging.getLogger(__name__)


def log_a(level: int, key: str, **kwargs):
    logger = logging.getLogger(__name__)
    message = get_message(key, **kwargs)
    logger.log(level, message)
