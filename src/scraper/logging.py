"""Structured logging configuration using structlog.

Provides JSON output for production and human-readable console output for development.
All logging throughout the project should use get_logger() instead of print().
"""

import logging
import sys

import structlog


def setup_logging(json_output: bool = False, log_level: str = "INFO") -> None:
    """Configure structlog with appropriate processors and output format.

    Args:
        json_output: If True, output JSON (production). If False, console format (dev).
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    # Convert string log level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure structlog processors
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    # Add renderer based on output format
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bridge stdlib logging to structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
    )
    logging.getLogger().handlers = []
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a logger instance bound with the module name.

    Args:
        name: Logger name (typically __name__ from calling module).

    Returns:
        Configured structlog logger with module name context.
    """
    return structlog.get_logger(name)
