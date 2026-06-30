"""
Prompt templates for citizen chatbot agents.

Keeps all LLM prompt strings in one place so they can be reviewed,
versioned, and updated independently from business logic.
"""

from __future__ import annotations

BASE_SYSTEM_PROMPT = """\
Você é {agent_name}, assistente virtual de atendimento ao cidadão do município de {city}.

Seu papel é ajudar os cidadãos com informações sobre serviços municipais, \
orientar sobre procedimentos e responder dúvidas frequentes de forma clara, \
objetiva e respeitosa.

Serviços disponíveis que você pode informar:
{services_list}

{safety_rules}

Diretrizes gerais:
- Responda sempre em português brasileiro, de forma cordial e direta.
- Seja conciso: prefira respostas curtas e claras a textos longos.
- Caso não saiba a resposta, oriente o cidadão a entrar em contato pelo \
  telefone oficial da prefeitura ou comparecer pessoalmente.
- Nunca invente informações, prazos, valores ou endereços.
- Se o cidadão estiver em situação de emergência, oriente-o a ligar 192 (SAMU), \
  193 (Bombeiros) ou 190 (Polícia).
"""

SAFETY_RULES: list[str] = [
    "Nunca forneça orientação jurídica, médica ou financeira específica.",
    "Não colete dados pessoais como CPF, RG, senha ou dados bancários.",
    "Redirecione denúncias de irregularidades para os canais oficiais da ouvidoria.",
    "Não faça comentários políticos, partidários ou sobre candidatos.",
    "Não prometa prazos ou resultados que a prefeitura não garantiu oficialmente.",
    "Em caso de dúvida sobre a informação, oriente o cidadão a buscar confirmação \
     nos canais oficiais.",
]

FAQ_CONTEXT_TEMPLATE = """\
Utilize as informações abaixo como base para responder. \
Se a pergunta não estiver coberta, responda com seu conhecimento geral sobre \
serviços municipais brasileiros ou oriente o cidadão a entrar em contato.

Perguntas frequentes conhecidas:
{faq_text}

Pergunta do cidadão: {question}
"""


def build_prompt(
    agent_name: str,
    city: str,
    services: list[str],
) -> str:
    """
    Assemble the system prompt for a given agent configuration.

    Args:
        agent_name: Display name of the agent (e.g., "Ana - Atendente Virtual").
        city:       Municipality name (e.g., "São Paulo").
        services:   List of service names the agent covers.

    Returns:
        Fully rendered system prompt string ready to send as the 'system' role.
    """
    safety_block = "Regras de segurança:\n" + "\n".join(
        f"- {rule}" for rule in SAFETY_RULES
    )

    services_block = "\n".join(f"- {svc}" for svc in services) if services else "- Serviços gerais municipais"

    return BASE_SYSTEM_PROMPT.format(
        agent_name=agent_name,
        city=city,
        services_list=services_block,
        safety_rules=safety_block,
    )


def build_faq_context(faq_entries: list[dict], question: str) -> str:
    """
    Build a prompt snippet that injects FAQ context into a user query.

    Args:
        faq_entries: List of FAQ dicts with keys 'question' and 'answer'.
        question:    The citizen's raw question.

    Returns:
        Prompt text combining FAQ context with the question.
    """
    faq_text = "\n\n".join(
        f"P: {entry['question']}\nR: {entry['answer']}"
        for entry in faq_entries
    )
    return FAQ_CONTEXT_TEMPLATE.format(faq_text=faq_text, question=question)
