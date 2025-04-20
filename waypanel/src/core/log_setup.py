import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional, Callable, Dict, Any

LOG_FILE_PATH = os.path.expanduser("~/.config/waypanel/waypanel.log")


class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors to log messages."""

    COLORS = {
        "DEBUG": "\033[94m",  # Blue
        "INFO": "\033[92m",  # Green
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "CRITICAL": "\033[95m",  # Magenta
        "RESET": "\033[0m",  # Reset color
    }

    def format(self, record):
        levelname = record.levelname
        message = super().format(record)
        if levelname in self.COLORS:
            message = f"{self.COLORS[levelname]}{message}{self.COLORS['RESET']}"
        return message


class ErrorHandler:
    """
    A centralized error-handling utility for managing exceptions, logging, and user notifications.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize the ErrorHandler with a logger instance.
        """
        self.logger = logger

    def handle(
        self,
        error: Exception,
        message: str = "An error occurred",
        level: str = "error",
        user_notification: Optional[Callable[[str], None]] = None,
        fallback: Optional[Callable[[], Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Handle an exception by logging it, notifying the user (if applicable),
        and executing a fallback mechanism.

        Args:
            error (Exception): The exception to handle.
            message (str): A custom error message to log and display.
            level (str): The logging level ('debug', 'info', 'warning', 'error', 'critical').
            user_notification (Callable[[str], None]): A function to notify the user (e.g., GUI alert).
            fallback (Callable[[], Any]): A fallback function to execute if the error occurs.
            context (Optional[Dict[str, Any]]): Additional contextual information to include in the log.
        """
        # Add contextual information to the message
        if context:
            context_str = ", ".join(f"{k}={v}" for k, v in context.items())
            message = f"{message} ({context_str})"

        # Log the error with the specified level
        log_method = getattr(self.logger, level.lower(), self.logger.error)
        log_method(f"{message}: {error}", exc_info=True)

        # Notify the user if a notification function is provided
        if user_notification:
            user_notification(message)

        # Execute the fallback mechanism if provided
        if fallback:
            try:
                fallback()
            except Exception as fallback_error:
                self.logger.error(
                    f"Fallback mechanism failed: {fallback_error}", exc_info=True
                )

    def report_to_server(self, error: Exception, endpoint: str) -> None:
        """
        Report the error to a remote monitoring server.

        Args:
            error (Exception): The exception to report.
            endpoint (str): The URL of the monitoring server.
        """
        import requests

        try:
            response = requests.post(
                endpoint,
                json={"error": str(error), "traceback": self._get_traceback(error)},
            )
            response.raise_for_status()
            self.logger.info("Error reported to monitoring server successfully.")
        except requests.RequestException as e:
            self.logger.error(f"Failed to report error to server: {e}", exc_info=True)

    @staticmethod
    def _get_traceback(error: Exception) -> str:
        """
        Extract the traceback of an exception as a string.

        Args:
            error (Exception): The exception to extract the traceback from.

        Returns:
            str: The formatted traceback.
        """
        import traceback

        return "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )

    @staticmethod
    def graceful_degradation(
        default_value: Any, func: Callable[..., Any], *args, **kwargs
    ) -> Any:
        """
        Execute a function with graceful degradation. If the function raises an exception,
        return the default value instead.

        Args:
            default_value (Any): The value to return if the function fails.
            func (Callable[..., Any]): The function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            Any: The result of the function or the default value if an error occurs.
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.getLogger("WaypanelLogger").error(
                f"Graceful degradation triggered: {e}"
            )
            return default_value


def setup_logging(level=logging.INFO) -> logging.Logger:
    """
    Configure logging with both file and console handlers.
    Ensures no duplicate handlers are added.

    Returns:
        logging.Logger: The configured logger instance.
    """
    logger = logging.getLogger("WaypanelLogger")
    logger.propagate = False  # Avoid duplicate logs

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

        # Console Handler with Colors
        console_handler = logging.StreamHandler()
        console_formatter = ColoredFormatter()
        console_handler.setFormatter(console_formatter)

        # Add handlers to the logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    # Attach ErrorHandler to the logger
    logger.error_handler = ErrorHandler(logger)

    return logger


# Example Usage
if __name__ == "__main__":
    logger = setup_logging()

    # Example function that may fail
    def risky_operation():
        raise ValueError("Something went wrong!")

    # Handle errors using the ErrorHandler
    logger.error_handler.handle(
        error=ValueError("Test error"),
        message="A test error occurred",
        level="error",
        user_notification=lambda msg: print(f"USER NOTIFICATION: {msg}"),
        fallback=lambda: print("Executing fallback mechanism..."),
    )

    # Graceful degradation example
    result = logger.error_handler.graceful_degradation(
        default_value="Default Value",
        func=risky_operation,
    )
    print(f"Result of risky operation: {result}")
