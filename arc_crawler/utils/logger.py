import logging
from typing import Dict

DEFAULT_FORMAT = "[%(levelname)s] %(message)s"


class FormatedLogger(logging.Formatter):
    def __init__(self, level_config: Dict[int, str] | None = None, *args, **kwargs):
        super().__init__(fmt=DEFAULT_FORMAT, *args, **kwargs)

        if level_config is None:
            level_config = {logging.DEBUG: "[%(levelname)s:%(name)s] %(message)s"}
        self._level_config = level_config

    def format(self, record):
        format_orig = self._style._fmt
        self._style._fmt = self._level_config.get(record.levelno, DEFAULT_FORMAT)
        formatted = super().format(record)
        self._style._fmt = format_orig
        return formatted
