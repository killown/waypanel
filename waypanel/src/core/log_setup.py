import os
import logging
from logging.handlers import RotatingFileHandler
import structlog
from structlog.stdlib import ProcessorFormatter, BoundLogger, add_logger_name
from structlog.processors import JSONRenderer, TimeStamper, add_log_level
from rich.logging import RichHandler
import colorama

# Define log file path
LOG_FILE_PATH = os.path.expanduser("~/.config/waypanel/waypanel.log")

# Ensure the log directory exists
os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)


def setup_logging(level=logging.DEBUG) -> BoundLogger:
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

    cr = structlog.dev.ConsoleRenderer(
        columns=[
            # Render the timestamp without the key name in yellow.
            structlog.dev.Column(
                "timestamp",
                structlog.dev.KeyValueColumnFormatter(
                    key_style=None,
                    value_style=colorama.Fore.YELLOW,
                    reset_style=colorama.Style.RESET_ALL,
                    value_repr=str,
                ),
            ),
            # Render the event without the key name in bright magenta.
            structlog.dev.Column(
                "event",
                structlog.dev.KeyValueColumnFormatter(
                    key_style=None,
                    value_style=colorama.Style.BRIGHT + colorama.Fore.MAGENTA,
                    reset_style=colorama.Style.RESET_ALL,
                    value_repr=str,
                ),
            ),
            # Default formatter for all keys not explicitly mentioned. The key is
            # cyan, the value is green.
            structlog.dev.Column(
                "",
                structlog.dev.KeyValueColumnFormatter(
                    key_style=colorama.Fore.CYAN,
                    value_style=colorama.Fore.GREEN,
                    reset_style=colorama.Style.RESET_ALL,
                    value_repr=str,
                ),
            ),
        ]
    )

    # Configure structlog processors
    # Configure structlog processors
    structlog.configure(
        processors=[
            add_log_level,  # Add log level (info, debug, etc.)
            add_logger_name,  # Add logger name
            TimeStamper(fmt="iso"),  # Timestamp in ISO format
            structlog.processors.StackInfoRenderer(),  # Include stack info if available
            structlog.processors.format_exc_info,  # Pretty-print exceptions
            cr if level <= logging.DEBUG else ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger("WaypanelLogger")


if __name__ == "__main__":
    logger = setup_logging(level=logging.DEBUG)
