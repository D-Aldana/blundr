"""OpenAI provider, and with OPENAI_BASE_URL any OpenAI-compatible endpoint —
Groq, OpenRouter, Together, Gemini's compatibility layer, LM Studio, vLLM.
"""

import os

from .. import config

DEFAULT_MODEL = "gpt-4o-mini"


def is_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


async def complete(system: str, user: str, model: str) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=config.OPENAI_BASE_URL or None)
    # OpenAI itself wants max_completion_tokens; the compatible servers behind a
    # custom base URL have settled on the older max_tokens.
    cap = "max_tokens" if config.OPENAI_BASE_URL else "max_completion_tokens"
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        **{cap: config.SUMMARY_MAX_TOKENS},
    )
    return (response.choices[0].message.content or "").strip()
