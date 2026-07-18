"""
Thin client for a locally-running Ollama server. This is the only "LLM call"
in the whole system, and it never leaves the local machine/network -
satisfying the "no external AI API" requirement.

Setup:
    1. Install Ollama: https://ollama.com
    2. Pull a model:   ollama pull llama3
    3. Ollama serves on http://localhost:11434 by default
"""
import requests

from app.config import settings


SYSTEM_PROMPT_TEMPLATE = """
You are the Zenfuture Digital Concierge, a professional and high-tech representative of Zenfuture Technologies. 

GUIDELINES:
1. IDENTITY: Speak as "We" (the Zenfuture team). Never refer to yourself as an AI, a bot, or a language model.
2. SOURCE MATERIAL: Use the provided context to answer. However, NEVER mention the words "context," "website," "documents," or "according to the info provided." 
3. MISSING INFO: If the answer is not in the context, do not say "I don't have that information." Instead, give a direct professional fallback. 
   Example: "For specific details on [Topic], please contact our specialist team at info@zenfuture.in so we can provide you with the most accurate update."
4. TONE: Tech-forward, elite, and extremely concise. No "fluff" or "filler" sentences.
5. VACANCIES/CAREERS: If asked about jobs and it's not in the context, say: "We are always looking for exceptional talent. Please submit your CV and portfolio to info@zenfuture.in for our HR team to review."

Context:
{context}
"""


def generate_reply(user_message: str, context: str) -> str:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        company_name=settings.company_name,
        context=context or "(no matching company information found)",
    )

    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
    }

    try:
        resp = requests.post(f"{settings.ollama_host}/api/chat", json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "").strip() or (
            "Sorry, I couldn't generate a response just now."
        )
    except requests.RequestException as e:
        # Ollama not running / model not pulled, etc.
        return (
            "I'm having trouble reaching the assistant engine right now. "
            "Please try again shortly, or leave your query and our team will follow up."
        )
