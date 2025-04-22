import os
import logging
from logging.handlers import RotatingFileHandler
import structlog
from structlog.stdlib import ProcessorFormatter, BoundLogger
from structlog.processors import JSONRenderer, TimeStamper, add_log_level
from structlog.dev import ConsoleRenderer
from rich.logging import RichHandler

# Define log file path
LOG_FILE_PATH = os.path.expanduser("~/.config/waypanel/waypanel.log")

# Ensure the log directory exists
os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)


class ErrorHandler:
    def __init__(self, logger_name="WaypanelLogger"):
        self.logger = structlog.get_logger(logger_name)

    def handle(
        self, error, message, level="error", context=None, user_notification=None
    ):
        """
        Centralized error handling and logging.

        Args:
            error (Exception): The exception or error to log.
            message (str): The log message.
            level (str): The log level (e.g., "debug", "info", "warning", "error").
            context (dict): Additional context to include in the log.
            user_notification (callable): A function to notify users (optional).
        """
        # Get the appropriate log method based on the level
        log_method = getattr(self.logger, level.lower(), self.logger.error)

        # Log the error with additional context
        log_method(
            message,
            error=str(error),
            context=context or {},
        )

        # Notify users if a notification function is provided
        if user_notification and callable(user_notification):
            user_notification(message)


def setup_logging(level=logging.INFO) -> BoundLogger:
    """
    Configure logging with both file and console handlers.
    Ensures no duplicate handlers are added.

    Returns:
        BoundLogger: The configured logger instance.
    """
    # Remove existing handlers to prevent duplicates
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Configure structlog processors
    structlog.configure(
        processors=[
            add_log_level,
            TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            ProcessorFormatter.wrap_for_formatter,  # Integrate with stdlib logging
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Create a logger
    logger = logging.getLogger("WaypanelLogger")
    logger.setLevel(level)

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
    logger.addHandler(file_handler)

    # Add RichHandler for console output
    console_handler = RichHandler(
        rich_tracebacks=True,  # Enable rich tracebacks
        markup=True,  # Enable Rich-style markup
        show_path=False,  # Hide log source file/line (optional)
    )
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console_handler)

    return structlog.get_logger("WaypanelLogger")


if __name__ == "__main__":
    logger = setup_logging(level=logging.DEBUG)
