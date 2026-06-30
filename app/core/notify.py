"""
Admin error notification via WhatsApp.

When an agent raises an unhandled exception, `notify_admin` is called by
BaseAgent.run(). This sends a WhatsApp message to the configured ADMIN_PHONE
so on-call engineers are alerted in real time without needing to check logs.

Flood prevention: the same error class+message prefix within 60 seconds
is silently suppressed using the same Redis dedup mechanism used for webhooks.
"""

from __future__ import annotations

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


def _error_key(error: Exception) -> str:
    """
    Build a stable dedup key for this error.

    Uses the exception class name + first 50 chars of the message so that
    a burst of the same OpenAI timeout only fires one WhatsApp alert.
    """
    return f"notify:{type(error).__name__}:{str(error)[:50]}"


async def notify_admin(error: Exception, context: dict) -> None:
    """
    Send a WhatsApp alert to ADMIN_PHONE about an unhandled agent error.

    Silently suppressed if:
    - ADMIN_PHONE is not configured.
    - The same error key was already sent within 60 seconds (flood guard).
    - The WhatsApp send itself fails (best-effort; never raises).

    Args:
        error:   The exception that was caught by BaseAgent.run().
        context: Dict of contextual fields to include in the alert
                 (agent name, session_id, etc.). Never include PII here.
    """
    if not settings.ADMIN_PHONE:
        logger.debug("notify_admin.no_admin_phone_configured")
        return

    # Import here to avoid circular dependency (notify <- dedup <- config)
    from app.core.dedup import is_duplicate

    key = _error_key(error)
    if await is_duplicate(key, ttl=60):
        logger.debug("notify_admin.suppressed_flood", error_key=key)
        return

    error_type = type(error).__name__
    context_str = " | ".join(f"{k}={v}" for k, v in context.items())
    text = (
        f"*[CHATBOT ERRO]* {error_type}\n"
        f"{str(error)[:200]}\n"
        f"Contexto: {context_str}"
    )

    try:
        # Import lazily to support deployments that only use Chatwoot (no Evolution)
        from app.integrations.whatsapp import send_message
        await send_message(settings.ADMIN_PHONE, text)
        logger.info("notify_admin.sent", error_type=error_type)
    except Exception as send_exc:
        # Never let notify failure cascade — just log it
        logger.error("notify_admin.send_failed", error=repr(send_exc))
