"""`get_composer()` reads LLM_PROVIDER. A real provider without a key falls
back to the stub with a warning, so development never calls a provider by
accident."""

import logging

from django.conf import settings

from .base import Composer
from .stub import StubComposer

log = logging.getLogger(__name__)


def get_composer() -> Composer:
    provider = settings.LLM_PROVIDER
    if provider == "stub":
        return StubComposer()
    if provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            log.warning("LLM_PROVIDER=anthropic without ANTHROPIC_API_KEY; using the stub composer")
            return StubComposer()
        from .anthropic import AnthropicComposer

        return AnthropicComposer(api_key=settings.ANTHROPIC_API_KEY, model=settings.LLM_MODEL)
    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            log.warning("LLM_PROVIDER=openai without OPENAI_API_KEY; using the stub composer")
            return StubComposer()
        from .openai import OpenAIComposer

        return OpenAIComposer(api_key=settings.OPENAI_API_KEY, model=settings.LLM_MODEL)
    raise ValueError(f"Unknown LLM_PROVIDER={provider!r}. Use stub, anthropic or openai.")
