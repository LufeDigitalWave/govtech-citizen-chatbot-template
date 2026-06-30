"""
Tests for EchoAgent and BaseAgent.run() error handling.
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.agents.echo_agent import EchoAgent


@pytest.mark.asyncio
async def test_echo_agent_returns_prefixed_message():
    agent = EchoAgent()
    result = await agent.process(
        session_id="test-session",
        message="Olá, preciso de ajuda",
        metadata={},
    )
    assert result == "Echo: Olá, preciso de ajuda"


@pytest.mark.asyncio
async def test_echo_agent_name():
    agent = EchoAgent()
    assert agent.name == "Echo Agent"


@pytest.mark.asyncio
async def test_base_agent_run_calls_notify_on_error():
    """BaseAgent.run() must call notify_admin and re-raise on process() failure."""

    class BrokenAgent(EchoAgent):
        async def process(self, session_id, message, metadata):
            raise ValueError("simulated failure")

    agent = BrokenAgent()

    with patch("app.agent.base.notify_admin", new_callable=AsyncMock) as mock_notify:
        with pytest.raises(ValueError, match="simulated failure"):
            await agent.run("session-1", "hello", {})

        mock_notify.assert_awaited_once()
        call_kwargs = mock_notify.call_args
        assert isinstance(call_kwargs.kwargs["error"], ValueError)
