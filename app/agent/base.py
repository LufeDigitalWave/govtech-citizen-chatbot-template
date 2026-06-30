"""
BaseAgent - Abstract base class for all citizen chatbot agents.

Every concrete agent extends this class and implements `process()`.
The `run()` method wraps process with error handling and admin notification.
"""

from __future__ import annotations

import abc
import structlog

from app.core.notify import notify_admin

logger = structlog.get_logger(__name__)


class BaseAgent(abc.ABC):
    """
    Abstract base class for all citizen service agents.

    Subclasses must implement:
        - process(session_id, message, metadata) -> str
        - name (property)

    Example::

        class MyAgent(BaseAgent):
            name = "My City Agent"

            async def process(self, session_id, message, metadata):
                return "Hello from MyAgent!"
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable display name for this agent (logged, shown in admin alerts)."""
        ...

    @abc.abstractmethod
    async def process(
        self,
        session_id: str,
        message: str,
        metadata: dict,
    ) -> str:
        """
        Core agent logic. Receives a citizen message, returns a reply string.

        Args:
            session_id: Stable identifier for the conversation (Chatwoot conversation_id,
                        WhatsApp phone number, etc.). Used for dedup and conversation state.
            message:    Raw text sent by the citizen.
            metadata:   Integration-specific extras (contact_name, inbox_id, phone, etc.).

        Returns:
            The agent's reply text, ready to be sent back to the citizen.
        """
        ...

    async def run(
        self,
        session_id: str,
        message: str,
        metadata: dict,
    ) -> str:
        """
        Public entry point called by the webhook router.

        Wraps `process()` with:
        - Structured logging (session_id, agent name, message length).
        - Exception capture + admin notification via WhatsApp.
        - Re-raises the exception so the router can return HTTP 500.

        Args:
            session_id: Stable conversation identifier.
            message:    Raw citizen message text.
            metadata:   Integration-specific extras.

        Returns:
            Reply string from `process()`.

        Raises:
            Exception: Any exception raised by `process()` is re-raised after
                       notifying the admin.
        """
        log = logger.bind(
            agent=self.name,
            session_id=session_id,
            msg_len=len(message),
        )
        log.info("agent.run.start")

        try:
            reply = await self.process(session_id, message, metadata)
            log.info("agent.run.ok", reply_len=len(reply))
            return reply

        except Exception as exc:
            log.error("agent.run.error", error=repr(exc))
            await notify_admin(
                error=exc,
                context={
                    "agent": self.name,
                    "session_id": session_id,
                    "msg_len": len(message),
                },
            )
            raise
