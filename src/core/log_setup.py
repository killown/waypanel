import os
import logging
from logging.handlers import RotatingFileHandler
import structlog
from structlog.stdlib import ProcessorFormatter, BoundLogger, add_logger_name
from structlog.processors import (
    JSONRenderer,
    TimeStamper,
    add_log_level,
    StackInfoRenderer,
    format_exc_info,
)
from rich.logging import RichHandler
from structlog.dev import ConsoleRenderer


XDG_STATE_HOME = os.environ.get("XDG_STATE_HOME") or os.path.expanduser(
    "~/.local/state"
)
APP_DIR = "waypanel"

LOG_FILE_PATH = os.path.join(XDG_STATE_HOME, APP_DIR, "waypanel.log")

os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)

LOGGER_NAME = None
os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)


class SpamFilter(logging.Filter):
    """Filters out repetitive log messages and works before structlog processing."""

    _config_reload_count = 0

    def filter(self, record):
        message = record.getMessage()
        if (
            record.levelno == logging.WARNING
            and "not found in in_use_buttons" in message
        ):
            return False
        if message == "Configuration reloaded successfully.":
            SpamFilter._config_reload_count += 1
            if SpamFilter._config_reload_count > 1:
                return False
        elif message == "Configuration file modified. Reloading...":
            if SpamFilter._config_reload_count >= 1:
                return False
        else:
            SpamFilter._config_reload_count = 0
        return True


def setup_logging(level: int = logging.DEBUG) -> BoundLogger:
    """
    Configures logging using structlog with separate handlers:
    - Console (RichHandler, no logger name)
    - File (JSON, with logger name)
    """
    new_time_format = "%Y-%m-%d %H:%M:%S"
    json_processors = [
        add_log_level,
        add_logger_name,
        TimeStamper(fmt=new_time_format, utc=False),
        StackInfoRenderer(),
        format_exc_info,
    ]
    console_pre_chain = [
        add_log_level,
        TimeStamper(fmt=new_time_format, utc=False),
        StackInfoRenderer(),
        format_exc_info,
    ]
    structlog.configure(
        processors=console_pre_chain
        + [
            ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    std_logger = logging.getLogger(LOGGER_NAME)
    std_logger.setLevel(level)
    std_logger.propagate = False
    for handler in std_logger.handlers[:]:
        std_logger.removeHandler(handler)
    spam_filter = SpamFilter()
    file_handler = RotatingFileHandler(
        LOG_FILE_PATH,
        maxBytes=1024 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.addFilter(spam_filter)
    json_formatter = ProcessorFormatter(
        foreign_pre_chain=json_processors,
        processor=JSONRenderer(),
    )
    file_handler.setFormatter(json_formatter)
    std_logger.addHandler(file_handler)
    console_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_path=False,
        show_time=False,
    )
    console_handler.setLevel(level)
    console_handler.addFilter(spam_filter)
    console_formatter_final = ProcessorFormatter(
        foreign_pre_chain=console_pre_chain,
        processor=ConsoleRenderer(colors=False),
        fmt="%(message)s",
    )
    console_handler.setFormatter(console_formatter_final)
    std_logger.addHandler(console_handler)
    return structlog.get_logger(LOGGER_NAME)
