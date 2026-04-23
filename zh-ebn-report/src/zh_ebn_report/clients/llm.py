"""Backend-agnostic LLM client protocol + factory.

The pipeline no longer talks to ``AnthropicClient`` directly. Instead, callers
depend on the :class:`LLMClient` protocol and obtain an instance via
:func:`make_llm_client`, which chooses between:

- ``LLM_BACKEND=claude_code`` (default) — shells out to the ``claude`` CLI,
  using the user's subscription session. No ``ANTHROPIC_API_KEY`` required.
- ``LLM_BACKEND=anthropic`` — direct Anthropic SDK, uses
  ``ANTHROPIC_API_KEY`` or ``LLM_API_KEY`` as before.

Both implementations must honour the same ``complete`` / ``complete_json``
signatures so that ``pipeline/agents.py`` can stay backend-agnostic.
"""

from __future__ import annotations

import shutil
from typing import Any, Literal, Protocol

from ..config import LlmConfig

ModelTier = Literal["haiku", "sonnet", "opus"]


class CachedSystemBlock(Protocol):
    """Structural reference — both backends use the concrete dataclass from
    :mod:`clients.anthropic`. Declared here for typing without a circular
    import: the Claude Code backend treats ``cache_control`` as a no-op (the
    CLI manages its own prompt cache)."""

    text: str
    cache: bool


class LLMClient(Protocol):
    """Minimum surface the pipeline expects from an LLM backend."""

    def model_for(self, tier: ModelTier) -> str: ...

    async def complete(
        self,
        *,
        tier: ModelTier,
        system_blocks: list[Any],
        user_message: str,
        max_tokens: int = ...,
        temperature: float = ...,
        json_mode: bool = ...,
    ) -> str: ...

    async def complete_json(
        self,
        *,
        tier: ModelTier,
        system_blocks: list[Any],
        user_message: str,
        max_tokens: int = ...,
        temperature: float = ...,
    ) -> dict[str, Any]: ...


def _auto_detect_backend() -> str:
    """Prefer Claude Code CLI when the ``claude`` binary is on PATH; fall
    back to Anthropic API otherwise. Overridden by ``LLM_BACKEND`` env."""

    if shutil.which("claude") is not None:
        return "claude_code"
    return "anthropic"


def make_llm_client(cfg: LlmConfig) -> LLMClient:
    """Construct the LLM client matching ``cfg.backend``.

    Lazy imports avoid loading the Anthropic SDK when the user runs through
    Claude Code CLI only (and vice versa).
    """

    backend = cfg.backend
    if backend == "auto":
        backend = _auto_detect_backend()

    if backend == "claude_code":
        # Lazy import so users without the Anthropic SDK can still run through
        # the CLI backend. PLC0415 is intentional here.
        from .claude_code_cli import ClaudeCodeCliClient  # noqa: PLC0415

        return ClaudeCodeCliClient(cfg)

    if backend == "anthropic":
        from .anthropic import AnthropicClient  # noqa: PLC0415

        return AnthropicClient(cfg)

    raise ValueError(
        f"Unknown LLM_BACKEND={backend!r}; expected 'claude_code' | 'anthropic' | 'auto'"
    )
