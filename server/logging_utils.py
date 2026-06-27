import datetime
import logging
import logging.config
import os
from pathlib import Path
from typing import Optional

import json5
from babel.core import Locale
from babel.dates import format_datetime
from babel.numbers import format_decimal, format_percent
from colorama import Fore, Style

_current_locale = "en"
_babel_locale = Locale("en")
_translations = {}


class ColoredFormatter(logging.Formatter):
    babel_locale = None
    LEVEL_COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }

    def __init__(
        self, fmt=None, datefmt=None, style="%", validate=True, *, defaults=None
    ):
        super().__init__(fmt, datefmt, style, validate, defaults=defaults)

    def formatTime(self, record, datefmt=None):
        locale = self.babel_locale or _babel_locale
        dt = datetime.datetime.fromtimestamp(record.created)
        return format_datetime(dt, format="medium", locale=locale)

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
    lib_config = config.get("logging_lib_config")
    locale_config = config.get("global_logging_config", {})
    return lib_config, locale_config


def load_translations(path=None):
    global _translations
    if path is None:
        path = str(_BASE_DIR / "config" / "locales")

    for lang_file in os.listdir(path):
        if lang_file.endswith(".json5"):
            lang = lang_file.replace(".json5", "")
            with open(f"{path}/{lang_file}") as f:
                _translations[lang] = json5.load(f).get(lang, {})

    return _translations


def set_locale(lang: str, locale_format: Optional[str] = None):
    global _current_locale, _babel_locale
    if lang in _translations:
        _current_locale = lang
        _babel_locale = Locale(locale_format or lang)
        ColoredFormatter.babel_locale = _babel_locale
    else:
        print(
            f"⚠️  Language '{lang}' not found. Available: {list(_translations.keys())}"
        )


def _format_message(message: str, **kwargs) -> str:
    formatted_kwargs = {}
    for key, value in kwargs.items():
        if isinstance(value, (int, float)):
            formatted_kwargs[key] = format_decimal(value, locale=_babel_locale)
        elif isinstance(value, float) and 0 <= value <= 1:
            formatted_kwargs[key] = format_percent(value, locale=_babel_locale)
        else:
            formatted_kwargs[key] = str(value)

    try:
        return message.format(**formatted_kwargs)
    except KeyError as e:
        print(f"⚠️  Missing parameter {e} for message '{message}'")
        return message


def get_message(key: str, **kwargs) -> str:
    message = _translations.get(_current_locale, {}).get(key, key)

    if kwargs:
        try:
            message = _format_message(message, **kwargs)
        except KeyError as e:
            print(f"⚠️  Missing parameter {e} for key '{key}'")

    return message


def setup_logging():
    logging.ColoredFormatter = ColoredFormatter
    load_translations()
    logging_config, locale_config = load_logging_config()
    set_locale(
        locale_config.get("logs_locale_lang", "en"),
        locale_config.get("logs_locale_format", "en"),
    )
    logging.config.dictConfig(config=logging_config)
    return logging.getLogger(__name__)


def ulog(level: int, key: str, **kwargs):
    logger = logging.getLogger(__name__)
    message = get_message(key, **kwargs)
    logger.log(level, message)
