"""Claude Code CLI LLM backend.

Shells out to ``claude -p`` (Claude Code CLI) instead of calling the Anthropic
SDK directly. This lets pipeline users run the whole pipeline through their
Claude subscription — no ``ANTHROPIC_API_KEY`` needed.

Implementation notes:

* One subprocess per LLM call. Concurrent ``asyncio.gather`` calls (e.g. the
  CASP parallel phase) spawn N concurrent ``claude`` processes, which is
  fine: each has its own session and independent stdin/stdout pipes.
* System prompts are long (≈60KB for the knowledge base blocks), so they go
  via ``--append-system-prompt-file <tempfile>`` rather than as a command-line
  argument to avoid ARG_MAX and shell-escaping hazards.
* User message arrives via stdin (``--input-format text``) for the same
  reason — prompts may contain arbitrary UTF-8 including quotes/newlines.
* The CLI emits one JSON line on stdout when ``--output-format json`` is set;
  the actual model text lives in the ``result`` field. We extract that,
  then the calling ``complete_json`` method parses *that* string as JSON.
* ``max_tokens`` / ``temperature`` are currently no-ops for this backend —
  the Claude Code CLI does not expose them via flags (and on a subscription
  the user pays by plan, not by token).
* Retries use the same tenacity policy as :class:`~.anthropic.AnthropicClient`
  so transient failures (network, stalled subprocess) surface the same way.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import LlmConfig
from .anthropic import CachedSystemBlock  # reuse the concrete dataclass

log = logging.getLogger(__name__)

ModelTier = Literal["haiku", "sonnet", "opus"]

# Per-subprocess timeout. The longest single call in the pipeline today is
# the Opus synthesiser on ~20KB of CASP JSON — in practice under 90s. This
# is the upper bound before tenacity retries.
_DEFAULT_SUBPROCESS_TIMEOUT_S = 180


class ClaudeCodeCliError(RuntimeError):
    """Raised when the ``claude`` CLI exits non-zero or produces malformed output."""


class ClaudeCodeCliClient:
    """Drop-in replacement for :class:`AnthropicClient` backed by ``claude -p``."""

    def __init__(
        self,
        cfg: LlmConfig,
        *,
        claude_bin: str | None = None,
        timeout_s: int = _DEFAULT_SUBPROCESS_TIMEOUT_S,
    ):
        self._cfg = cfg
        self._claude_bin = claude_bin or os.getenv("CLAUDE_BIN") or "claude"
        self._timeout_s = timeout_s

    def model_for(self, tier: ModelTier) -> str:
        mapping = {
            "haiku": self._cfg.haiku_model,
            "sonnet": self._cfg.sonnet_model,
            "opus": self._cfg.opus_model,
        }
        return mapping[tier]

    async def complete(
        self,
        *,
        tier: ModelTier,
        system_blocks: list[CachedSystemBlock],
        user_message: str,
        max_tokens: int = 4096,  # noqa: ARG002  CLI has no token cap
        temperature: float = 0.2,  # noqa: ARG002  CLI has no temperature knob
        json_mode: bool = False,
    ) -> str:
        """Invoke ``claude -p`` once and return the model's text output.

        ``max_tokens`` / ``temperature`` are accepted for interface parity
        with the Anthropic backend but ignored — the CLI does not surface
        them.
        """

        system_text = _concatenate_system_blocks(system_blocks)
        if json_mode:
            user_message = (
                user_message
                + "\n\n請以合法 JSON 回應，不要加任何說明文字或 markdown code fence。"
            )

        model = self.model_for(tier)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(4),
            wait=wait_exponential(multiplier=2, min=2, max=30),
            retry=retry_if_exception_type((TimeoutError, ClaudeCodeCliError)),
            reraise=True,
        ):
            with attempt:
                result_text = await self._exec_once(
                    model=model,
                    system_text=system_text,
                    user_message=user_message,
                )
                return result_text
        # Unreachable (reraise=True), but satisfies mypy.
        raise ClaudeCodeCliError("exhausted retries without a response")

    async def complete_json(
        self,
        *,
        tier: ModelTier,
        system_blocks: list[CachedSystemBlock],
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        raw = await self.complete(
            tier=tier,
            system_blocks=system_blocks,
            user_message=user_message,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=True,
        )
        return _parse_model_json(raw)

    # ---------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------
    async def _exec_once(
        self,
        *,
        model: str,
        system_text: str,
        user_message: str,
    ) -> str:
        """Run one ``claude -p`` subprocess; return the extracted ``result`` text."""

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".txt",
            delete=False,
        ) as sys_file:
            sys_file.write(system_text)
            sys_path = Path(sys_file.name)

        try:
            proc = await asyncio.create_subprocess_exec(
                self._claude_bin,
                "-p",
                "--model",
                model,
                "--output-format",
                "json",
                "--input-format",
                "text",
                "--append-system-prompt-file",
                str(sys_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(input=user_message.encode("utf-8")),
                    timeout=self._timeout_s,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                raise
        finally:
            # Always clean up the tempfile, even if the subprocess raised.
            sys_path.unlink(missing_ok=True)

        if proc.returncode != 0:
            stderr = stderr_b.decode("utf-8", errors="replace")
            raise ClaudeCodeCliError(
                f"claude -p exited {proc.returncode}: {stderr[:400]}"
            )

        return _extract_result_text(stdout_b.decode("utf-8", errors="replace"))


def _concatenate_system_blocks(blocks: list[CachedSystemBlock]) -> str:
    """Flatten the structured system blocks into one string.

    The Anthropic backend uses ``cache_control`` markers on individual
    blocks; the Claude Code CLI does its own prompt caching based on the
    hash of the full text, so concatenation is safe and lossless.
    """

    return "\n\n".join(b.text for b in blocks)


def _extract_result_text(stdout: str) -> str:
    """Parse Claude Code's JSON wrapper and return the model's ``result`` text.

    Expected shape::

        {"type":"result","subtype":"success","is_error":false,
         "result":"<model output>", "session_id":"…", ...}

    When ``is_error`` is true, the CLI still exits 0 in some cases — we
    surface the error rather than returning garbage.
    """

    stdout = stdout.strip()
    if not stdout:
        raise ClaudeCodeCliError("claude -p produced empty stdout")
    # The CLI emits one JSON object per invocation; if multiple lines are
    # present (e.g. some future streaming mode), take the last non-empty line.
    last_line = next(
        (line for line in reversed(stdout.splitlines()) if line.strip()),
        stdout,
    )
    try:
        wrapper = json.loads(last_line)
    except json.JSONDecodeError as e:
        raise ClaudeCodeCliError(
            f"stdout is not valid JSON ({e}); first 200 chars: {stdout[:200]!r}"
        ) from e

    if wrapper.get("is_error"):
        raise ClaudeCodeCliError(
            f"claude -p reported is_error=True; "
            f"status={wrapper.get('api_error_status')}; "
            f"result={str(wrapper.get('result'))[:200]!r}"
        )
    result = wrapper.get("result")
    if not isinstance(result, str):
        raise ClaudeCodeCliError(
            f"missing 'result' string in CLI output; keys={list(wrapper.keys())}"
        )
    return result


def _parse_model_json(raw: str) -> dict[str, Any]:
    """Strip optional markdown fences and parse the model's JSON text."""

    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)
