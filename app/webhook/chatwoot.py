"""
FastAPI router for Chatwoot webhook events.

POST /webhook/chatwoot receives all events from a Chatwoot inbox.
The handler:
1. Optionally validates an HMAC-SHA256 signature.
2. Parses the payload (ignores non-message events).
3. Deduplicates using the message ID via Redis.
4. Loads the configured agent and calls agent.run().
5. Sends the reply back to Chatwoot.

Always returns HTTP 200 for events that are parsed but skipped (no message,
duplicate, wrong event type) so Chatwoot does not retry them endlessly.
Returns HTTP 500 only for genuine processing errors after the agent is invoked.
"""

from __future__ import annotations

import hashlib
import hmac
import structlog

from fastapi import APIRouter, Header, HTTPException, Request, Response

from app.core.config import settings
from app.core.dedup import is_duplicate
from app.integrations import chatwoot as cw

logger = structlog.get_logger(__name__)

router = APIRouter()


def _verify_signature(body: bytes, signature: str | None) -> None:
    """
    Validate the Chatwoot webhook HMAC-SHA256 signature.

    Skipped entirely when WEBHOOK_SECRET is not configured (suitable for
    internal/private deployments). In production, always set WEBHOOK_SECRET.

    Args:
        body:      Raw request body bytes.
        signature: Value of the X-Chatwoot-Signature header.

    Raises:
        HTTPException(401): If signature is required but missing or invalid.
    """
    if not settings.WEBHOOK_SECRET:
        return

    if not signature:
        raise HTTPException(status_code=401, detail="Missing webhook signature")

    expected = hmac.new(
        settings.WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature.removeprefix("sha256=")):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


def _load_agent():
    """
    Instantiate the configured agent class.

    Agents are loaded per-request so configuration changes via env var
    are picked up on restart without code changes.

    Returns:
        A concrete BaseAgent instance.

    Raises:
        ValueError: If AGENT_TYPE is not a recognized agent name.
    """
    agent_type = settings.AGENT_TYPE.lower()

    if agent_type == "faq":
        from app.agents.faq_agent import FAQAgent
        return FAQAgent()

    if agent_type == "echo":
        from app.agents.echo_agent import EchoAgent
        return EchoAgent()

    raise ValueError(f"Unknown AGENT_TYPE: {settings.AGENT_TYPE!r}. Must be 'faq' or 'echo'.")


@router.post("/webhook/chatwoot", tags=["webhooks"])
async def chatwoot_webhook(
    request: Request,
    x_chatwoot_signature: str | None = Header(default=None),
) -> Response:
    """
    Receive and process Chatwoot webhook events.

    Accepts all Chatwoot event types; only `message_created` with incoming
    messages triggers agent processing. All other events return 200 immediately.
    """
    body = await request.body()
    _verify_signature(body, x_chatwoot_signature)

    try:
        payload = await request.json()
    except Exception:
        logger.warning("webhook.chatwoot.invalid_json")
        return Response(status_code=200)

    parsed = cw.parse_webhook(payload)
    if parsed is None:
        logger.debug("webhook.chatwoot.ignored", event=payload.get("event"))
        return Response(status_code=200)

    session_id: str = parsed["session_id"]
    message: str = parsed["message"]
    metadata: dict = parsed["metadata"]
    conversation_id: int = metadata["conversation_id"]

    # Dedup using Chatwoot message ID if available, else fall back to content hash
    msg_obj = payload.get("message", {})
    event_id = str(msg_obj.get("id") or f"{session_id}:{hash(message)}")

    if await is_duplicate(event_id):
        logger.info("webhook.chatwoot.deduped", event_id=event_id)
        return Response(status_code=200)

    log = logger.bind(session_id=session_id, conversation_id=conversation_id)
    log.info("webhook.chatwoot.processing")

    # Send typing indicator (best-effort, fire-and-forget)
    try:
        await cw.send_typing(conversation_id)
    except Exception:
        pass

    try:
        agent = _load_agent()
        reply = await agent.run(session_id, message, metadata)
        await cw.send_message(conversation_id, reply)
        log.info("webhook.chatwoot.replied")
        return Response(status_code=200)

    except Exception as exc:
        log.error("webhook.chatwoot.agent_error", error=repr(exc))
        # Return 500 so upstream monitoring catches it, but Chatwoot will NOT retry
        # message_created events on 500 — this is intentional to avoid reply floods.
        raise HTTPException(status_code=500, detail="Agent processing failed") from exc
