"""LLM provider abstraction.

FOCL talks to a single LLM endpoint to compress code. Two providers are
supported:

- ``anthropic`` — the native Anthropic Messages API (default). Uses adaptive
  thinking and the exact ``count_tokens`` endpoint.
- ``openrouter`` — any model exposed through OpenRouter's OpenAI-compatible
  Chat Completions API (``anthropic/claude-*``, ``openai/gpt-*``,
  ``google/gemini-*``, …). Requires the optional ``openai`` package.
- ``claude-code`` — runs the locally installed Claude Code CLI headless
  (``claude -p``), so it uses whatever account Claude Code is logged in with
  (e.g. a Claude subscription) and needs no API key of its own.

The rest of the codebase passes an :class:`LLMConfig` around and calls
:func:`generate_text` / :func:`count_tokens`; it never imports a vendor SDK
directly, so adding a provider only touches this module.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

ANTHROPIC = "anthropic"
OPENROUTER = "openrouter"
CLAUDE_CODE = "claude-code"
PROVIDERS = (ANTHROPIC, OPENROUTER, CLAUDE_CODE)

DEFAULT_PROVIDER = ANTHROPIC

# Default model per provider. OpenRouter expects ``vendor/model`` slugs.
DEFAULT_MODELS = {
    ANTHROPIC: "claude-opus-4-7",
    OPENROUTER: "anthropic/claude-opus-4-7",
    # Claude Code model aliases always resolve to the latest model of a tier.
    CLAUDE_CODE: "opus",
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
        """Return the provider's API key, or raise if it's missing.

        ``claude-code`` authenticates through the Claude Code CLI itself, so
        it needs no key: this returns "" after checking the CLI is installed.
        """
        if self.provider == CLAUDE_CODE:
            _claude_executable()
            return ""
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
    if config.provider == CLAUDE_CODE:
        return _claude_code_generate(config, system, user_message, max_tokens)
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
# Claude Code CLI (headless `claude -p`)
# ---------------------------------------------------------------------------

# Generous: a large shard can take several minutes to compress.
_CLAUDE_CODE_TIMEOUT = 1800

# Turn the agent into a plain completion endpoint: our system prompt replaces
# Claude Code's, no tools, no MCP servers, no user/project settings (so no
# hooks or plugins fire), no skills, no saved session. Deliberately NOT --bare:
# it only accepts ANTHROPIC_API_KEY, which would defeat using a subscription.
_CLAUDE_CODE_FLAGS = (
    "--output-format", "json",
    "--tools", "",
    "--strict-mcp-config",
    "--setting-sources", "",
    "--disable-slash-commands",
    "--no-session-persistence",
)


def _claude_executable() -> str:
    exe = shutil.which("claude")
    if exe is None:
        raise RuntimeError(
            "The 'claude-code' provider needs the Claude Code CLI ('claude') on "
            "PATH. Install it from https://claude.com/claude-code and log in, "
            "or use --provider anthropic/openrouter with an API key."
        )
    return exe


def _claude_code_command(exe: str, config: LLMConfig, system_file: Path) -> list[str]:
    return [exe, "-p", "--model", config.model,
            "--system-prompt-file", str(system_file), *_CLAUDE_CODE_FLAGS]


def _claude_code_generate(config: LLMConfig, system: str, user_message: str,
                          max_tokens: int) -> str:
    """Run one completion through ``claude -p`` and return its text.

    The (potentially huge) user message goes through stdin and the system
    prompt through a file, so neither hits command-line length limits. It runs
    in an empty temp dir so no project CLAUDE.md is picked up.
    """
    exe = _claude_executable()
    env = dict(os.environ, CLAUDE_CODE_MAX_OUTPUT_TOKENS=str(max_tokens))
    with tempfile.TemporaryDirectory(prefix="focl-cc-") as tmp:
        system_file = Path(tmp) / "system.txt"
        system_file.write_text(system, encoding="utf-8")
        try:
            proc = subprocess.run(
                _claude_code_command(exe, config, system_file),
                input=user_message, capture_output=True, text=True,
                encoding="utf-8", errors="replace", cwd=tmp, env=env,
                timeout=_CLAUDE_CODE_TIMEOUT,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"Claude Code did not answer within {_CLAUDE_CODE_TIMEOUT}s."
            ) from e
    return _parse_claude_code_output(proc.returncode, proc.stdout, proc.stderr)


def _parse_claude_code_output(returncode: int, stdout: str, stderr: str) -> str:
    """Extract the text from ``claude -p --output-format json``, or raise."""
    try:
        data = json.loads(stdout)
    except ValueError:
        detail = (stderr or stdout).strip()[:500] or f"exit code {returncode}"
        raise RuntimeError(f"Claude Code failed: {detail}") from None
    if not isinstance(data, dict):
        raise RuntimeError(f"Claude Code returned unexpected output: {stdout[:200]}")
    if data.get("is_error") or returncode != 0:
        message = str(data.get("result") or stderr.strip() or f"exit code {returncode}")
        raise RuntimeError(f"Claude Code error: {message}")
    return str(data.get("result") or "").strip()


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
