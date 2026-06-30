"""
Chatwoot integration helpers.

Covers:
- Sending messages and typing indicators to a conversation.
- Parsing inbound webhooks into a normalized dict.

All HTTP calls use a shared AsyncClient with a 10-second timeout.
The client is module-level and reused across requests (safe for async).
"""

from __future__ import annotations

import structlog
import httpx

from app.core.config import settings

logger = structlog.get_logger(__name__)

_TIMEOUT = httpx.Timeout(10.0)


def _client() -> httpx.AsyncClient:
    """Return a configured AsyncClient for the Chatwoot API."""
    return httpx.AsyncClient(
        base_url=settings.CHATWOOT_URL.rstrip("/"),
        headers={
            "api_access_token": settings.CHATWOOT_API_TOKEN,
            "Content-Type": "application/json",
        },
        timeout=_TIMEOUT,
        follow_redirects=True,
    )


async def send_message(conversation_id: int, content: str) -> None:
    """
    Post a bot reply to a Chatwoot conversation.

    Args:
        conversation_id: Chatwoot conversation ID (integer).
        content:         Text content to send.

    Raises:
        httpx.HTTPStatusError: If Chatwoot returns a non-2xx status.
    """
    url = (
        f"/api/v1/accounts/{settings.CHATWOOT_ACCOUNT_ID}"
        f"/conversations/{conversation_id}/messages"
    )
    payload = {
        "content": content,
        "message_type": "outgoing",
        "private": False,
    }
    async with _client() as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
    logger.info("chatwoot.send_message.ok", conversation_id=conversation_id)


async def send_typing(conversation_id: int) -> None:
    """
    Send a typing indicator to a Chatwoot conversation.

    This is best-effort; errors are logged but not raised so a typing
    failure never breaks the main message flow.

    Args:
        conversation_id: Chatwoot conversation ID.
    """
    url = (
        f"/api/v1/accounts/{settings.CHATWOOT_ACCOUNT_ID}"
        f"/conversations/{conversation_id}/typing_status"
    )
    try:
        async with _client() as client:
            resp = await client.post(url, json={"typing_status": "on"})
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("chatwoot.send_typing.failed", error=repr(exc))


def parse_webhook(body: dict) -> dict | None:
    """
    Parse a raw Chatwoot webhook payload into a normalized message dict.

    Only handles `message_created` events where the message is incoming
    and has a non-empty content string. Returns None for anything else
    (outgoing messages, status updates, assignment events, etc.) so the
    webhook router knows to silently acknowledge and skip.

    Args:
        body: Raw JSON body dict from the Chatwoot webhook POST.

    Returns:
        Dict with keys:
            session_id (str):   Chatwoot conversation ID as string.
            message (str):      Raw message text from the citizen.
            metadata (dict):    Additional context:
                conversation_id (int)
                contact_name (str)
                inbox_id (int)
                account_id (int)
        Or None if the event should be ignored.
    """
    event = body.get("event")
    if event != "message_created":
        return None

    msg = body.get("message", {})
    message_type = msg.get("message_type")  # 0 = incoming, 1 = outgoing
    content: str = msg.get("content") or ""

    # Ignore outgoing messages (bot's own replies) and empty content
    if message_type != 0 or not content.strip():
        return None

    conversation = body.get("conversation", {})
    conversation_id: int = conversation.get("id", 0)
    contact = body.get("contact", {})

    return {
        "session_id": str(conversation_id),
        "message": content.strip(),
        "metadata": {
            "conversation_id": conversation_id,
            "contact_name": contact.get("name", "Cidadão"),
            "inbox_id": conversation.get("inbox_id"),
            "account_id": body.get("account", {}).get("id"),
        },
    }
