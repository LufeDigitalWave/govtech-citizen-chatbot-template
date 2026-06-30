"""
Tests for the Chatwoot webhook parser.
"""

import pytest
from app.integrations.chatwoot import parse_webhook


def _make_payload(event="message_created", message_type=0, content="Olá"):
    return {
        "event": event,
        "message": {
            "id": 42,
            "content": content,
            "message_type": message_type,
        },
        "conversation": {"id": 99, "inbox_id": 3},
        "contact": {"name": "Cidadão Teste"},
        "account": {"id": 1},
    }


def test_parse_incoming_message():
    result = parse_webhook(_make_payload())
    assert result is not None
    assert result["session_id"] == "99"
    assert result["message"] == "Olá"
    assert result["metadata"]["conversation_id"] == 99
    assert result["metadata"]["contact_name"] == "Cidadão Teste"


def test_parse_ignores_outgoing_message():
    result = parse_webhook(_make_payload(message_type=1))
    assert result is None


def test_parse_ignores_wrong_event():
    result = parse_webhook(_make_payload(event="conversation_created"))
    assert result is None


def test_parse_ignores_empty_content():
    result = parse_webhook(_make_payload(content="   "))
    assert result is None


def test_parse_ignores_none_content():
    payload = _make_payload()
    payload["message"]["content"] = None
    result = parse_webhook(payload)
    assert result is None
