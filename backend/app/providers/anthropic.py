"""Anthropic provider — the default when ANTHROPIC_API_KEY is set."""

import os

from .. import config

DEFAULT_MODEL = "claude-haiku-4-5"


def is_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


async def complete(system: str, user: str, model: str) -> str:
    # Imported here so the SDK is only needed by people who use this provider.
    import anthropic

    client = anthropic.AsyncAnthropic()
    # No output_config.effort: Haiku 4.5, the default here, rejects it.
    response = await client.messages.create(
        model=model,
        max_tokens=config.SUMMARY_MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()
