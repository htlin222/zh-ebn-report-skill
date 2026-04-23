"""AuditedLLMClient — dump every LLM call to an ArtifactStore.

Wraps any object that satisfies the :class:`~.llm.LLMClient` protocol
(``AnthropicClient`` or ``ClaudeCodeCliClient``). The wrapper is transparent
to pipeline callers: same ``complete`` / ``complete_json`` / ``model_for``
surface, same return types.

The caller's function name (e.g. ``run_topic_gatekeeper``) is detected by
inspecting the call stack at the time ``complete()`` is invoked. This way
we do not need to change any pipeline signature to thread a ``caller_tag``
through — the existing subagent code continues to work unmodified.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any, Literal

from ..pipeline.audit import ArtifactStore

log = logging.getLogger(__name__)

ModelTier = Literal["haiku", "sonnet", "opus"]


def _detect_caller() -> str:
    """Return the nearest pipeline-level function name on the call stack.

    We walk up frames until we find something that lives under
    ``zh_ebn_report.pipeline`` (skipping internal helpers inside this
    wrapper and the LLM client itself). Falls back to ``"unknown"``.
    """

    frame = sys._getframe()
    try:
        while frame is not None:
            name = frame.f_code.co_name
            module = frame.f_globals.get("__name__", "")
            if (
                module.startswith("zh_ebn_report.pipeline")
                and not name.startswith("_")
                and name not in {"complete", "complete_json"}
            ):
                return name
            frame = frame.f_back
    except Exception:  # noqa: BLE001  (stack walk is best-effort)
        pass
    return "unknown"


class AuditedLLMClient:
    """Wrap an ``LLMClient`` and persist every call via ``ArtifactStore``."""

    def __init__(self, inner: Any, store: ArtifactStore, backend_name: str):
        self._inner = inner
        self._store = store
        self._backend = backend_name

    def model_for(self, tier: ModelTier) -> str:
        # Pure pass-through — no artifact to log for a trivial lookup.
        return self._inner.model_for(tier)

    async def complete(
        self,
        *,
        tier: ModelTier,
        system_blocks: list[Any],
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        caller = _detect_caller()
        t0 = time.monotonic()
        raw = await self._inner.complete(
            tier=tier,
            system_blocks=system_blocks,
            user_message=user_message,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=json_mode,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        # system_blocks items are dataclass-like (``CachedSystemBlock``).
        system_texts = [self._extract_text(b) for b in system_blocks]
        self._store.dump_llm_call(
            caller=caller,
            tier=tier,
            model=self._inner.model_for(tier),
            backend=self._backend,
            system_texts=system_texts,
            user_message=user_message,
            response_raw=raw,
            response_parsed=None,
            duration_ms=elapsed_ms,
            json_mode=json_mode,
        )
        return raw

    async def complete_json(
        self,
        *,
        tier: ModelTier,
        system_blocks: list[Any],
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        caller = _detect_caller()
        t0 = time.monotonic()
        parsed = await self._inner.complete_json(
            tier=tier,
            system_blocks=system_blocks,
            user_message=user_message,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        system_texts = [self._extract_text(b) for b in system_blocks]
        # Re-serialize the parsed dict for audit (LLM raw text isn't exposed
        # by complete_json; the parsed payload IS the audit value here).
        raw_approx = json.dumps(parsed, ensure_ascii=False, indent=2)
        self._store.dump_llm_call(
            caller=caller,
            tier=tier,
            model=self._inner.model_for(tier),
            backend=self._backend,
            system_texts=system_texts,
            user_message=user_message,
            response_raw=raw_approx,
            response_parsed=parsed,
            duration_ms=elapsed_ms,
            json_mode=True,
        )
        return parsed

    @staticmethod
    def _extract_text(block: Any) -> str:
        # Works for both the ``CachedSystemBlock`` dataclass and any object
        # with a ``text`` attribute; string blocks pass through untouched.
        if isinstance(block, str):
            return block
        return getattr(block, "text", str(block))
