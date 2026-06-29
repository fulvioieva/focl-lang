"""LLM provider abstraction.

FOCL talks to a single LLM endpoint to compress code. Two providers are
supported:

- ``anthropic`` — the native Anthropic Messages API (default). Uses adaptive
  thinking and the exact ``count_tokens`` endpoint.
- ``openrouter`` — any model exposed through OpenRouter's OpenAI-compatible
  Chat Completions API (``anthropic/claude-*``, ``openai/gpt-*``,
  ``google/gemini-*``, …). Requires the optional ``openai`` package.

The rest of the codebase passes an :class:`LLMConfig` around and calls
:func:`generate_text` / :func:`count_tokens`; it never imports a vendor SDK
directly, so adding a provider only touches this module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ANTHROPIC = "anthropic"
OPENROUTER = "openrouter"
PROVIDERS = (ANTHROPIC, OPENROUTER)

DEFAULT_PROVIDER = ANTHROPIC

# Default model per provider. OpenRouter expects ``vendor/model`` slugs.
DEFAULT_MODELS = {
    ANTHROPIC: "claude-opus-4-7",
    OPENROUTER: "anthropic/claude-opus-4-7",
}

# Env var holding the API key for each provider.
API_KEY_ENV = {
    ANTHROPIC: "ANTHROPIC_API_KEY",
    OPENROUTER: "OPENROUTER_API_KEY",
}

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Characters-per-token heuristic for the offline estimator. Source code averages
# ~3.5 chars/token with the Claude tokenizer; 3.0 stays conservative.
_CHARS_PER_TOKEN = 3.0


@dataclass
class LLMConfig:
    """Resolved configuration for a single LLM provider/model."""

    provider: str = DEFAULT_PROVIDER
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None

    def __post_init__(self) -> None:
        if self.provider not in PROVIDERS:
            raise ValueError(
                f"Unknown provider '{self.provider}'. Choose one of: {', '.join(PROVIDERS)}."
            )
        if not self.model:
            self.model = DEFAULT_MODELS[self.provider]
        if self.provider == OPENROUTER and not self.base_url:
            self.base_url = OPENROUTER_BASE_URL

    def require_api_key(self) -> str:
        key = self.api_key or os.environ.get(API_KEY_ENV[self.provider])
        if not key:
            env = API_KEY_ENV[self.provider]
            raise ValueError(
                f"API key not found for provider '{self.provider}'. "
                f"Set {env} or pass --api-key."
            )
        return key


def estimate_tokens(text: str) -> int:
    """Fast offline estimate of token count based on character length."""
    return int(len(text) / _CHARS_PER_TOKEN) + 1


def count_tokens(config: LLMConfig, text: str, use_api_counter: bool = False) -> int:
    """Count tokens for ``text`` under ``config``.

    Exact counting is only available on the Anthropic provider (via its
    ``count_tokens`` endpoint). For OpenRouter — and whenever the API call
    fails or no key is present — fall back to the offline estimate.
    """
    if use_api_counter and config.provider == ANTHROPIC:
        key = config.api_key or os.environ.get(API_KEY_ENV[ANTHROPIC])
        if key:
            try:
                client = _anthropic_client(config, key)
                result = client.messages.count_tokens(
                    model=config.model,
                    messages=[{"role": "user", "content": text}],
                )
                return int(result.input_tokens)
            except Exception:
                pass
    return estimate_tokens(text)


def generate_text(config: LLMConfig, system: str, user_message: str,
                  max_tokens: int) -> str:
    """Send a single system+user request and return the model's text output.

    Streams the response (long generations would otherwise risk HTTP timeouts)
    and concatenates the text parts.
    """
    key = config.require_api_key()
    if config.provider == ANTHROPIC:
        return _anthropic_generate(config, key, system, user_message, max_tokens)
    return _openrouter_generate(config, key, system, user_message, max_tokens)


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


def _anthropic_client(config: LLMConfig, key: str):
    import anthropic

    kwargs = {"api_key": key}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return anthropic.Anthropic(**kwargs)


def _anthropic_generate(config: LLMConfig, key: str, system: str,
                        user_message: str, max_tokens: int) -> str:
    client = _anthropic_client(config, key)
    with client.messages.stream(
        model=config.model,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        result = stream.get_final_message()

    parts = [block.text for block in result.content if hasattr(block, "text")]
    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# OpenRouter (OpenAI-compatible)
# ---------------------------------------------------------------------------


def _openrouter_generate(config: LLMConfig, key: str, system: str,
                         user_message: str, max_tokens: int) -> str:
    try:
        from openai import OpenAI
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "OpenRouter support requires the 'openai' package. "
            "Install it with: pip install 'focl[openrouter]'"
        ) from e

    client = OpenAI(api_key=key, base_url=config.base_url or OPENROUTER_BASE_URL)
    stream = client.chat.completions.create(
        model=config.model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        stream=True,
    )

    parts: list[str] = []
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            parts.append(delta.content)
    return "".join(parts).strip()
