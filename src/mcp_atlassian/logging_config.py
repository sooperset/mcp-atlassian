"""Advanced logging configuration for MCP Atlassian."""

import logging
import os
import sys
import threading
import time
import types
import uuid
from collections.abc import Callable, Mapping
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar, cast

# Type for callable return value
T = TypeVar("T")

# Default logger configuration
DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] [%(context)s] %(message)s"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_DIRECTORY = "logs"
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5


class ContextualLogger(logging.Logger):
    """Logger that maintains context between related operations."""

    def __init__(self, name: str, level: int = 0) -> None:
        """Initialize the contextual logger."""
        super().__init__(name, level)
        self._context_data = threading.local()

    def _get_context_str(self) -> str:
        """Get the current context string."""
        context_data = getattr(self._context_data, "data", {})
        if not context_data:
            return "no-context"

        # Format context as: operation=X,trace_id=Y,...
        return ",".join(f"{k}={v}" for k, v in context_data.items())

    def _log(
        self,
        level: int,
        msg: object,
        args: tuple[object, ...] | Mapping[str, object],
        exc_info: Any = None,
        extra: Mapping[str, object] | None = None,
        stack_info: bool = False,
        stacklevel: int = 1,
    ) -> None:
        """Overrides _log method to include context."""
        if extra is None:
            extra = {}

        # Adds context information
        if "context" not in extra:
            # Create a copy to avoid modifying the original dict
            extra = dict(extra)
            extra["context"] = self._get_context_str()

        # Passes to original implementation
        super()._log(level, msg, args, exc_info, extra, stack_info, stacklevel + 1)

    def set_context(self, **kwargs: Any) -> None:
        """
        Sets context values for the logger.

        Args:
            **kwargs: Key-value pairs to add to the context
        """
        if not hasattr(self._context_data, "data"):
            self._context_data.data = {}

        # Updates context
        self._context_data.data.update(kwargs)

    def clear_context(self) -> None:
        """Removes all context data from the logger."""
        if hasattr(self._context_data, "data"):
            self._context_data.data = {}

    def with_context(
        self, **context: Any
    ) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """
        Returns a decorator that executes a function with specific context.

        Args:
            **context: Context values to be set during execution

        Returns:
            Decorator that applies the context
        """

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> T:
                # Saves current context
                old_context = getattr(self._context_data, "data", {}).copy()

                # Sets new context
                self.set_context(**context)

                # Adds trace_id if it doesn't exist
                if "trace_id" not in getattr(self._context_data, "data", {}):
                    self.set_context(trace_id=str(uuid.uuid4())[:8])

                try:
                    return func(*args, **kwargs)
                finally:
                    # Restores previous context
                    self._context_data.data = old_context

            return wrapper

        return decorator


class LoggingContextManager:
    """Context manager for logging with tracking."""

    def __init__(
        self, logger: ContextualLogger, operation: str, **context: Any
    ) -> None:
        """
        Initializes the logging context manager.

        Args:
            logger: Contextual logger
            operation: Name of the operation being executed
            **context: Additional context data
        """
        self.logger = logger
        self.operation = operation
        self.context = context.copy()
        self.start_time = time.time()

        # Generates a trace_id if not provided
        self.trace_id = context.get("trace_id", str(uuid.uuid4())[:8])

    def __enter__(self) -> "LoggingContextManager":
        """Starts the logging context."""
        # Saves current context
        self.old_context = getattr(self.logger._context_data, "data", {}).copy()

        # Sets new context
        self.context["operation"] = self.operation
        self.context["trace_id"] = self.trace_id

        # Saves context in the logger
        self.logger.set_context(**self.context)

        # Logs operation start
        self.logger.info(f"Operation started: {self.operation}")

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Finalizes the logging context."""
        # Calculates duration
        duration = time.time() - self.start_time

        # Logs operation end
        if exc_type:
            self.logger.error(
                f"Operation failed: {self.operation} after {duration:.3f}s - {exc_val}"
            )
        else:
            self.logger.debug(
                f"Operation completed: {self.operation} in {duration:.3f}s"
            )

        # Restores previous context
        self.logger._context_data.data = self.old_context


def setup_logger(
    name: str = "mcp-atlassian",
    level: str = None,
    log_to_file: bool = True,
    log_dir: str = None,
    log_format: str = None,
) -> ContextualLogger:
    """
    Configures and returns a contextual logger.

    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, etc.)
        log_to_file: If True, logs to file
        log_dir: Directory to store log files
        log_format: Log format

    Returns:
        Configured contextual logger
    """
    # Replaces the default factory to use ContextualLogger
    logging.setLoggerClass(ContextualLogger)

    # Creates/gets the logger
    logger = logging.getLogger(name)

    # Sets log level
    log_level = level or os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)
    logger.setLevel(getattr(logging, log_level.upper()))

    # Sets format
    formatter = logging.Formatter(log_format or os.getenv("LOG_FORMAT", DEFAULT_FORMAT))

    # Handler for console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Handler for file if needed
    if log_to_file:
        log_directory = log_dir or os.getenv("LOG_DIR", DEFAULT_LOG_DIRECTORY)

        # Ensures the directory exists
        Path(log_directory).mkdir(parents=True, exist_ok=True)

        # Creates handler with file rotation
        from logging.handlers import RotatingFileHandler

        log_file = Path(log_directory) / f"{name}.log"
        file_handler = RotatingFileHandler(
            log_file, maxBytes=MAX_LOG_SIZE, backupCount=LOG_BACKUP_COUNT
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Prevents propagation to the root logger
    logger.propagate = False

    return cast(ContextualLogger, logger)


def log_operation(
    logger: ContextualLogger, operation: str, **context: Any
) -> LoggingContextManager:
    """
    Creates a context manager for operation logging.

    Args:
        logger: Contextual logger
        operation: Name of the operation
        **context: Additional context data

    Returns:
        Context manager configured for operation logging
    """
    return LoggingContextManager(logger, operation, **context)


def log_function(
    operation: str = None, **context: Any
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for automatic function logging.

    Args:
        operation: Operation name (default: function name)
        **context: Additional context data

    Returns:
        Configured decorator
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        op_name = operation or func.__name__

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Gets the appropriate logger
            logger_name = func.__module__
            logger = cast(ContextualLogger, logging.getLogger(logger_name))

            # Uses function name as operation if not specified
            op_name = operation if operation else func.__name__

            # Executes in logging context
            with LoggingContextManager(logger, op_name, **context):
                return func(*args, **kwargs)

        return wrapper

    return decorator
