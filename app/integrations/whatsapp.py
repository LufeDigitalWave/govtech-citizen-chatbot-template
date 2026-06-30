"""
WhatsApp integration helpers via Evolution API.

Evolution API is a self-hosted WhatsApp unofficial gateway commonly used
in Brazilian automations. The same pattern works with other compatible
gateways (UAZAPI, WPPConnect) by adjusting the endpoint paths.

Docs: https://doc.evolution-api.com
"""

from __future__ import annotations

import re
import structlog
import httpx

from app.core.config import settings

logger = structlog.get_logger(__name__)

_TIMEOUT = httpx.Timeout(10.0)

# Strip any WhatsApp JID suffix before storing/logging phone numbers.
_JID_RE = re.compile(r"@(s\.whatsapp\.net|lid|c\.us)$")


def _normalize_phone(raw: str) -> str:
    """Remove WhatsApp JID suffix and any non-digit prefix noise."""
    return _JID_RE.sub("", raw).strip()


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.EVOLUTION_URL.rstrip("/"),
        headers={
            "apikey": settings.EVOLUTION_API_KEY,
            "Content-Type": "application/json",
        },
        timeout=_TIMEOUT,
        follow_redirects=True,
    )


async def send_message(phone: str, text: str) -> None:
    """
    Send a text message to a WhatsApp number via Evolution API.

    The phone number is normalized (JID suffix stripped) before sending.
    Evolution API expects the number in E.164 format without the '+'.

    Args:
        phone: WhatsApp phone number or JID (e.g., "5511999999999@s.whatsapp.net").
        text:  Message content.

    Raises:
        httpx.HTTPStatusError: If Evolution API returns a non-2xx status.
    """
    clean_phone = _normalize_phone(phone)
    url = f"/message/sendText/{settings.EVOLUTION_INSTANCE}"
    payload = {
        "number": clean_phone,
        "text": text,
        "delay": 500,
    }
    async with _client() as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
    logger.info("whatsapp.send_message.ok", phone_len=len(clean_phone))


def parse_webhook(body: dict) -> dict | None:
    """
    Parse a raw Evolution API webhook payload into a normalized message dict.

    Handles the `messages.upsert` event for incoming text messages.
    Returns None for status updates, media-only messages, group events,
    or any payload that should be silently ignored.

    The phone number is never included in the returned dict to avoid
    accidental PII logging downstream. Use session_id (which equals the
    normalized phone) for routing.

    Args:
        body: Raw JSON body dict from the Evolution API webhook POST.

    Returns:
        Dict with keys:
            session_id (str):  Normalized phone number (used as conversation key).
            message (str):     Raw text from the citizen.
            metadata (dict):   Additional context:
                instance (str)
                message_id (str)
                from_me (bool)
                push_name (str)
        Or None if the event should be ignored.
    """
    event = body.get("event")
    if event not in ("messages.upsert", "MESSAGES_UPSERT"):
        return None

    data = body.get("data", {})

    # Prefer senderJid when present (group messages, etc.)
    sender_jid: str = data.get("senderJid") or data.get("key", {}).get("remoteJid", "")
    from_me: bool = data.get("key", {}).get("fromMe", False)

    if from_me:
        return None  # Ignore bot's own outgoing echoes

    if not sender_jid:
        return None

    # Only handle text messages
    message_content = (
        data.get("message", {}).get("conversation")
        or data.get("message", {}).get("extendedTextMessage", {}).get("text")
        or ""
    )

    if not message_content.strip():
        return None

    phone = _normalize_phone(sender_jid)
    message_id: str = data.get("key", {}).get("id", "")

    return {
        "session_id": phone,
        "message": message_content.strip(),
        "metadata": {
            "instance": body.get("instance", settings.EVOLUTION_INSTANCE),
            "message_id": message_id,
            "from_me": from_me,
            "push_name": data.get("pushName", ""),
        },
    }
