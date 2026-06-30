# GovTech Citizen Chatbot Template

[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Docker Swarm](https://img.shields.io/badge/Docker-Swarm%20compatible-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/engine/swarm/)

Production-ready framework for building AI-powered citizen service chatbots connected to WhatsApp or Chatwoot. Used in Brazilian municipal government deployments to answer citizen questions about taxes, permits, social services, and urban infrastructure — automating thousands of monthly interactions with zero code changes between municipalities.

---

## Why this template exists

Brazilian municipal governments receive high volumes of repetitive citizen inquiries through WhatsApp. This framework provides a hardened base that handles the operational complexity (webhook dedup, error alerting, PII-safe logging, Docker Swarm compatibility) so each new deployment only needs to supply a FAQ file and a system prompt.

---

## Key design decisions

| Decision | Why |
|---|---|
| **BaseAgent pattern** | Swap OpenAI for any LLM, or add a retrieval-augmented agent, without touching the webhook layer |
| **Redis dedup** | Idempotent webhook processing — safe under Chatwoot retries and multi-replica Swarm deployments |
| **PII-safe structured logging** | CPF, phone, email values are replaced with `[REDACTED]` before any log output |
| **Admin notifications on errors** | On-call engineers receive WhatsApp alerts when an agent raises an unhandled exception; flood guard prevents storms |
| **Docker Swarm compatible** | `deploy:` block in compose, multi-stage Dockerfile, non-root container user |

---

## Architecture

```
Citizen
  |
  | WhatsApp message
  v
Evolution API (or Chatwoot inbox)
  |
  | POST /webhook/chatwoot
  v
┌─────────────────────────────────────────────┐
│  FastAPI Webhook Router                      │
│  1. HMAC signature verify (optional)         │
│  2. parse_webhook() → session_id + message   │
│  3. Redis dedup (SET NX / TTL 60s)           │
│  4. send_typing() indicator                  │
└────────────────┬────────────────────────────┘
                 │
                 v
        ┌────────────────┐
        │  BaseAgent.run │  ← catches exceptions → notify_admin()
        └───────┬────────┘
                │
                v
        ┌────────────────┐
        │  agent.process │
        │  (FAQAgent)    │
        │  1. Keyword    │
        │     search FAQ │
        │  2. OpenAI     │
        │     gpt-4.1    │
        └───────┬────────┘
                │ reply text
                v
        chatwoot.send_message()
                |
                v
            Citizen sees reply
```

---

## Project structure

```
govtech-citizen-chatbot-template/
├── app/
│   ├── agent/
│   │   ├── base.py          # BaseAgent abstract class
│   │   └── prompts.py       # System prompt templates + safety rules
│   ├── agents/
│   │   ├── faq_agent.py     # FAQ + OpenAI fallback (production)
│   │   └── echo_agent.py    # Echo agent (testing/demo)
│   ├── core/
│   │   ├── config.py        # Pydantic Settings (all env vars)
│   │   ├── dedup.py         # Redis SET NX deduplication
│   │   ├── logging.py       # structlog + PII redaction processor
│   │   └── notify.py        # Admin WhatsApp error notifications
│   ├── integrations/
│   │   ├── chatwoot.py      # Chatwoot API + webhook parser
│   │   └── whatsapp.py      # Evolution API + webhook parser
│   ├── webhook/
│   │   └── chatwoot.py      # FastAPI router POST /webhook/chatwoot
│   └── main.py              # App entry point, /health endpoint
├── agents/
│   └── faq/
│       └── faq_data.yaml    # Example FAQ data (edit per municipality)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Creating a new agent

Three steps to add a custom agent:

**Step 1 — Extend BaseAgent**

```python
# app/agents/my_agent.py
from app.agent.base import BaseAgent

class MyAgent(BaseAgent):
    name = "Assistente da Prefeitura de Campinas"

    async def process(self, session_id: str, message: str, metadata: dict) -> str:
        # Your logic here: call OpenAI, query a database, hit an API...
        return f"Olá! Você disse: {message}"
```

**Step 2 — Register in the webhook router**

```python
# app/webhook/chatwoot.py  (inside _load_agent())
if agent_type == "my":
    from app.agents.my_agent import MyAgent
    return MyAgent()
```

**Step 3 — Set in environment**

```bash
AGENT_TYPE=my
```

That's it. The webhook router, dedup, logging, and error notifications all work automatically.

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/LufeDigitalWave/govtech-citizen-chatbot-template.git
cd govtech-citizen-chatbot-template

# 2. Configure
cp .env.example .env
# Edit .env — at minimum set AGENT_TYPE=echo for a smoke test (no OpenAI needed)

# 3. Start services
docker compose up -d

# 4. Expose locally with ngrok (for Chatwoot webhook)
ngrok http 8000
# Copy the HTTPS URL: https://xxxx.ngrok.io

# 5. Register webhook in Chatwoot
# Settings > Integrations > Webhooks > New Webhook
# URL: https://xxxx.ngrok.io/webhook/chatwoot
# Events: message_created

# 6. Test with curl
curl -X POST http://localhost:8000/webhook/chatwoot \
  -H "Content-Type: application/json" \
  -d '{
    "event": "message_created",
    "message": {"content": "Qual o horário de atendimento?", "message_type": 0, "id": "test-001"},
    "conversation": {"id": 1, "inbox_id": 1},
    "contact": {"name": "Cidadão Teste"},
    "account": {"id": 1}
  }'

# 7. Check health
curl http://localhost:8000/health
```

To switch to the full FAQ agent with OpenAI:

```bash
# In .env
AGENT_TYPE=faq
OPENAI_API_KEY=sk-proj-...
AGENT_CITY=Campinas

# Restart
docker compose up -d api
```

Edit `agents/faq/faq_data.yaml` to add your municipality's real FAQ content.

---

## Production deployment (Docker Swarm)

```bash
# Build and push image
docker build -t your-registry.io/govtech-chatbot:latest .
docker push your-registry.io/govtech-chatbot:latest

# Deploy stack
docker stack deploy -c docker-compose.yml chatbot

# Rolling update with zero downtime (update_config: start-first is set)
docker service update \
  --image your-registry.io/govtech-chatbot:v1.1.0 \
  chatbot_api

# Inject secrets via Docker secrets (recommended over env vars for keys)
echo "sk-proj-..." | docker secret create openai_api_key -
docker service update \
  --secret-add openai_api_key \
  chatbot_api
```

Scale the API service independently of Redis (Redis stays on the manager):

```bash
docker service scale chatbot_api=4
```

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `AGENT_TYPE` | `faq` | Agent to load: `faq` or `echo` |
| `AGENT_CITY` | `Município` | City name in system prompt |
| `FAQ_PATH` | `agents/faq/faq_data.yaml` | Path to FAQ YAML |
| `OPENAI_API_KEY` | — | Required for FAQAgent |
| `OPENAI_MODEL` | `gpt-4.1` | OpenAI chat model |
| `CHATWOOT_URL` | — | Chatwoot base URL |
| `CHATWOOT_API_TOKEN` | — | Chatwoot user token |
| `CHATWOOT_ACCOUNT_ID` | `1` | Chatwoot account ID |
| `EVOLUTION_URL` | — | Evolution API base URL |
| `EVOLUTION_API_KEY` | — | Evolution API key |
| `EVOLUTION_INSTANCE` | `default` | Evolution instance name |
| `ADMIN_PHONE` | — | WhatsApp for error alerts |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `WEBHOOK_SECRET` | — | HMAC secret for webhook sig |
| `LOG_LEVEL` | `INFO` | Root log level |
| `JSON_LOGS` | `false` | JSON logs for aggregators |

---

## Running tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

---

## License

MIT — see [LICENSE](LICENSE).

Built with FastAPI, structlog, Redis, and OpenAI. Deployed in production for Brazilian municipal government citizen services.
