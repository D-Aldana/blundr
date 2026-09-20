"""LLM providers for the summary stage.

Each provider module exposes `DEFAULT_MODEL` and an async `complete(system,
user, model) -> str`. Nothing above this package knows which one is in play:
the summary guardrail validates whatever prose comes back, and any provider
failure falls back to the deterministic paragraph.
"""

from types import ModuleType

from .. import config
from . import anthropic, ollama, openai

PROVIDERS: dict[str, ModuleType] = {
    "anthropic": anthropic,
    "openai": openai,
    "ollama": ollama,
}

# Providers that can be picked without being named, in preference order. Ollama
# is absent on purpose: it has no credential to detect, so choosing it is always
# explicit.
_AUTODETECT = ("anthropic", "openai")


class ProviderError(RuntimeError):
    """Configuration is wrong in a way the operator has to fix."""


def resolve() -> tuple[str, ModuleType] | None:
    """The configured provider, or None when there is nothing to call.

    None is not an error — it's the no-API-key case, and the caller degrades to
    the deterministic summary.
    """
    name = config.LLM_PROVIDER
    if name:
        if name not in PROVIDERS:
            raise ProviderError(
                f"unknown LLM_PROVIDER {name!r}. "
                f"Available: {', '.join(sorted(PROVIDERS))}"
            )
        return name, PROVIDERS[name]

    for candidate in _AUTODETECT:
        if PROVIDERS[candidate].is_configured():
            return candidate, PROVIDERS[candidate]
    return None


def model_for(name: str) -> str:
    """SUMMARY_MODEL if set, else the provider's own default."""
    return config.SUMMARY_MODEL or PROVIDERS[name].DEFAULT_MODEL
