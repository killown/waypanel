import os
import logging
from logging.handlers import RotatingFileHandler
import structlog
from structlog.stdlib import ProcessorFormatter, BoundLogger
from structlog.processors import JSONRenderer, TimeStamper, add_log_level
from rich.logging import RichHandler

# Define log file path
LOG_FILE_PATH = os.path.expanduser("~/.config/waypanel/waypanel.log")

# Ensure the log directory exists
os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)


def setup_logging(level=logging.INFO) -> BoundLogger:
    """Configure logging with both file and console handlers.
    Ensures no duplicate handlers are added.

    Returns:
        BoundLogger: The configured logger instance.
    """
    print("Setting up logging...")  # Debug statement

    # Remove existing handlers to prevent duplicates
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create a logger
    logger = logging.getLogger("WaypanelLogger")
    if not logger.handlers:  # Only add handlers if none exist
        logger.setLevel(level)

        # File Handler with Rotation
        file_handler = RotatingFileHandler(
            LOG_FILE_PATH,
            maxBytes=1024 * 1024,  # 1 MB per log file
            backupCount=2,
        )
        file_handler.setLevel(level)

        # File formatter
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

        # Console formatter
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        console_handler.setLevel(level)
        logger.addHandler(console_handler)

        logger.propagate = False  # Disable propagation to the root logger

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

    return structlog.get_logger("WaypanelLogger")


if __name__ == "__main__":
    logger = setup_logging(level=logging.INFO)
