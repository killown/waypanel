import os
import logging
from logging.handlers import RotatingFileHandler

LOG_FILE_PATH = os.path.expanduser("~/.config/waypanel/waypanel.log")


class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors to log messages."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        log_message = super().format(record)
        log_level = record.levelname
        if log_level in self.COLORS:
            log_message = f"{self.COLORS[log_level]}{log_message}{self.RESET}"
        return log_message


def setup_logging(level=logging.INFO):
    """
    Configure logging with both file and console handlers.
    Ensures no duplicate handlers are added.
    """
    logger = logging.getLogger("WaypanelLogger")
    logger.propagate = False

    # Avoid adding multiple handlers to the same logger
    if not logger.handlers:
        logger.setLevel(level)

        # Ensure the log directory exists
        os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)

        # File Handler with Rotation
        file_handler = RotatingFileHandler(
            LOG_FILE_PATH,
            maxBytes=1024 * 1024,  # 1 MB per log file
            backupCount=2,
        )
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)

        if logger.hasHandlers():
            logger.handlers.clear()

        # Console Handler with Colors
        console_handler = logging.StreamHandler()
        console_formatter = ColoredFormatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)

        # Add handlers to the logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger
