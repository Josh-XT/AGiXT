"""
Custom logging configuration for uvicorn that redacts sensitive data.
"""

import logging
import re

# Patterns to match JWT tokens and other sensitive data
SENSITIVE_PATTERNS = [
    (re.compile(r"(authorization=)[^\s&\"'\]]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(api_key=)[^\s&\"'\]]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(token=)[^\s&\"'\]]+", re.IGNORECASE), r"\1[REDACTED]"),
]


def redact_sensitive_data(text):
    """Redact sensitive data from a string."""
    if not isinstance(text, str):
        return text
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


class SensitiveDataFilter(logging.Filter):
    """Filter to redact JWT tokens and other sensitive data from log messages."""

    def filter(self, record):
        # Handle direct message
        if record.msg:
            record.msg = redact_sensitive_data(str(record.msg))
        # Handle args - uvicorn uses %s formatting with args
        if record.args:
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    new_args.append(redact_sensitive_data(arg))
                else:
                    new_args.append(arg)
            record.args = tuple(new_args)
        return True


# Uvicorn logging configuration dict
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "sensitive_data_filter": {
            "()": SensitiveDataFilter,
        },
    },
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(levelprefix)s %(message)s",
            "use_colors": None,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "filters": ["sensitive_data_filter"],
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "filters": ["sensitive_data_filter"],
        },
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "level": "INFO",
        },
        "uvicorn.access": {
            "handlers": ["access"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
