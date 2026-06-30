"""
Echo Agent - Minimal demo agent for local development and webhook testing.

Returns every message prefixed with "Echo: " so you can verify the full
webhook -> dedup -> agent -> reply pipeline without an OpenAI key.
"""

from __future__ import annotations

from app.agent.base import BaseAgent


class EchoAgent(BaseAgent):
    """
    Demo agent that echoes the citizen's message back.

    Useful for:
    - Verifying webhook delivery end-to-end.
    - Integration tests without real LLM calls.
    - Smoke-testing a new deployment before switching to FAQAgent.

    Set AGENT_TYPE=echo in .env to activate.
    """

    name = "Echo Agent"

    async def process(
        self,
        session_id: str,
        message: str,
        metadata: dict,
    ) -> str:
        return f"Echo: {message}"
