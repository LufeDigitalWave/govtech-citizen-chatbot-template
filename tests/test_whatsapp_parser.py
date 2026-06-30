"""
Tests for the WhatsApp / Evolution API webhook parser.
"""

import pytest
from app.integrations.whatsapp import parse_webhook, _normalize_phone


def _make_payload(
    event="messages.upsert",
    from_me=False,
    content="Boa tarde",
    sender_jid="5511999887766@s.whatsapp.net",
):
    return {
        "event": event,
        "instance": "prefeitura-bot",
        "data": {
            "key": {
                "id": "msg-abc123",
                "remoteJid": sender_jid,
                "fromMe": from_me,
            },
            "message": {"conversation": content},
            "pushName": "Cidadão",
        },
    }


def test_parse_incoming_message():
    result = parse_webhook(_make_payload())
    assert result is not None
    assert result["session_id"] == "5511999887766"
    assert result["message"] == "Boa tarde"
    assert result["metadata"]["push_name"] == "Cidadão"


def test_parse_ignores_outgoing():
    result = parse_webhook(_make_payload(from_me=True))
    assert result is None


def test_parse_ignores_wrong_event():
    result = parse_webhook(_make_payload(event="connection.update"))
    assert result is None


def test_parse_ignores_empty_content():
    result = parse_webhook(_make_payload(content=""))
    assert result is None


def test_normalize_phone_strips_jid():
    assert _normalize_phone("5511999887766@s.whatsapp.net") == "5511999887766"
    assert _normalize_phone("5511999887766@lid") == "5511999887766"
    assert _normalize_phone("5511999887766@c.us") == "5511999887766"
    assert _normalize_phone("5511999887766") == "5511999887766"
