"""
Structured logging setup with PII redaction.

Uses structlog with a custom processor that replaces the values of known
PII fields with "[REDACTED]" before any output is written. This ensures
that CPF, phone numbers, emails, and passwords never appear in log files,
metrics exporters, or Sentry/Datadog integrations — even if a developer
accidentally passes them in a log call.

Call `setup_logging()` once at application startup (done in main.py).
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

# Fields whose VALUES must never appear in logs.
# Keys are matched case-insensitively.
PII_FIELDS: frozenset[str] = frozenset(
    {
        "cpf",
        "rg",
        "email",
        "phone",
        "telefone",
        "celular",
        "senha",
        "password",
        "token",
        "api_key",
        "secret",
        "credit_card",
        "cartao",
    }
)


def _pii_filter(
    logger: Any,  # noqa: ANN401
    method: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    structlog processor that redacts PII field values.

    Walks the event_dict and replaces the value of any key that matches
    a known PII field name with the string "[REDACTED]". Operates on
    the top-level dict only (does not recurse into nested dicts) to
    keep the processor fast and predictable.

    Args:
        logger:     The bound logger instance (unused by this processor).
        method:     Log level method name (unused by this processor).
        event_dict: The mutable event dictionary structlog passes through
                    the processor chain.

    Returns:
        The (potentially mutated) event_dict.
    """
    for key in list(event_dict.keys()):
        if key.lower() in PII_FIELDS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def setup_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    """
    Configure structlog for the application.

    In development (json_logs=False) logs are human-readable with colors.
    In production (json_logs=True) logs are JSON-formatted for log aggregators
    (Loki, CloudWatch, Datadog, etc.).

    Args:
        log_level:  Root log level as string (e.g., "INFO", "DEBUG").
        json_logs:  If True, output JSON. If False, output colored console.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _pii_filter,
    ]

    if json_logs:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())

    # Suppress noisy third-party loggers in production
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
