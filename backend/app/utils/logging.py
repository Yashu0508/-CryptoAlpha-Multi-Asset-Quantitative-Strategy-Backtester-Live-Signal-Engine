"""Structured logging configuration."""

import logging
from logging.config import dictConfig


def configure_logging(log_level: str) -> None:
    """Configure consistent stdout logging for application processes."""

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                }
            },
            "handlers": {
                "default": {"class": "logging.StreamHandler", "formatter": "standard"}
            },
            "root": {"handlers": ["default"], "level": log_level.upper()},
        }
    )
    logging.getLogger(__name__).debug("Logging configured")
