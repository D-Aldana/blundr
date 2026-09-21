"""Ollama provider — a model running on the user's own machine, no key, no cost.

Spoken to over its native /api/chat with httpx, which the project already
depends on, rather than through its OpenAI compatibility layer.
"""

import httpx

from .. import config

DEFAULT_MODEL = "llama3.2"


def is_configured() -> bool:
    # Nothing to detect — no credential exists. Selecting Ollama is always
    # explicit, via LLM_PROVIDER=ollama.
    return False


async def complete(system: str, user: str, model: str) -> str:
    async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT_S) as client:
        response = await client.post(
            f"{config.OLLAMA_HOST}/api/chat",
            json={
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "options": {"num_predict": config.SUMMARY_MAX_TOKENS},
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip()
