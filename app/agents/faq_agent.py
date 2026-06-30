"""
FAQ Agent - Knowledge base-first citizen service agent.

Strategy:
1. Search loaded FAQ for keyword matches.
2. If a match is found, use it as grounding context for the OpenAI call.
3. If no match, fall back to a generic OpenAI call with the system prompt only.

FAQ data is loaded from a YAML file at init time (path configurable via env).
"""

from __future__ import annotations

import os
from pathlib import Path

import openai
import structlog
import yaml

from app.agent.base import BaseAgent
from app.agent.prompts import build_faq_context, build_prompt
from app.core.config import settings

logger = structlog.get_logger(__name__)

_DEFAULT_FAQ_PATH = Path("agents/faq/faq_data.yaml")

# Services this agent can handle (shown in system prompt)
_SERVICES = [
    "Emissão de segunda via de IPTU e ISSQN",
    "Agendamento de serviços na prefeitura",
    "Informações sobre alvará e licença de funcionamento",
    "Coleta de lixo e limpeza urbana",
    "Iluminação pública",
    "Transporte público municipal",
    "Programas sociais e benefícios",
    "Ouvidoria e denúncias",
]


class FAQAgent(BaseAgent):
    """
    Agent that answers citizen questions using a structured FAQ + OpenAI fallback.

    The YAML FAQ file is loaded once at instantiation. No hot-reload;
    restart the service to pick up FAQ changes (suitable for Docker Swarm
    rolling restarts).
    """

    name = "Assistente de Atendimento ao Cidadão"

    def __init__(
        self,
        faq_path: str | Path | None = None,
        city: str | None = None,
    ) -> None:
        faq_path = Path(faq_path or os.getenv("FAQ_PATH", str(_DEFAULT_FAQ_PATH)))
        self._city = city or os.getenv("AGENT_CITY", "Município")
        self._faqs: list[dict] = []
        self._system_prompt = build_prompt(
            agent_name=self.name,
            city=self._city,
            services=_SERVICES,
        )
        self._client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self._load_faq(faq_path)

    def _load_faq(self, path: Path) -> None:
        if not path.exists():
            logger.warning("faq_agent.faq_not_found", path=str(path))
            return
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self._faqs = data.get("faqs", [])
        logger.info("faq_agent.faq_loaded", count=len(self._faqs), path=str(path))

    def _keyword_search(self, message: str) -> list[dict]:
        """
        Return FAQ entries whose keywords appear in the message.
        Case-insensitive, unaccented comparison not applied (YAML keywords
        should already be lowercase without diacritics for reliability).
        """
        msg_lower = message.lower()
        matches: list[dict] = []
        for entry in self._faqs:
            keywords: list[str] = entry.get("keywords", [])
            if any(kw.lower() in msg_lower for kw in keywords):
                matches.append(entry)
        return matches

    async def process(
        self,
        session_id: str,
        message: str,
        metadata: dict,
    ) -> str:
        log = logger.bind(session_id=session_id)

        matched = self._keyword_search(message)
        log.info("faq_agent.keyword_search", matches=len(matched))

        if matched:
            user_content = build_faq_context(matched, message)
        else:
            user_content = message

        response = await self._client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=512,
            temperature=0.3,
        )

        reply = response.choices[0].message.content or ""
        log.info("faq_agent.reply_generated", tokens=response.usage.total_tokens if response.usage else None)
        return reply.strip()
