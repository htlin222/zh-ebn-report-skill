"""Tests for the Claude Code CLI LLM backend.

Most tests are pure-Python (parse helpers + mocked subprocess). One optional
integration test is gated on ``CLAUDE_CODE_INTEGRATION=1`` so CI doesn't
spend the user's subscription on every run.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from unittest.mock import AsyncMock, patch

import pytest

from zh_ebn_report.clients.anthropic import CachedSystemBlock
from zh_ebn_report.clients.claude_code_cli import (
    ClaudeCodeCliClient,
    ClaudeCodeCliError,
    _extract_result_text,
    _parse_model_json,
)
from zh_ebn_report.config import LlmConfig


def _cfg(**overrides) -> LlmConfig:
    base = dict(
        backend="claude_code",
        api_key="",
        base_url=None,
        default_model="claude-sonnet-4-6",
        haiku_model="claude-haiku-4-5-20251001",
        sonnet_model="claude-sonnet-4-6",
        opus_model="claude-opus-4-7",
    )
    base.update(overrides)
    return LlmConfig(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
class TestExtractResultText:
    def test_extracts_result_from_success_wrapper(self) -> None:
        wrapper = json.dumps(
            {"type": "result", "is_error": False, "result": "HELLO"}
        )
        assert _extract_result_text(wrapper) == "HELLO"

    def test_error_wrapper_raises(self) -> None:
        wrapper = json.dumps(
            {
                "type": "result",
                "is_error": True,
                "api_error_status": 500,
                "result": "boom",
            }
        )
        with pytest.raises(ClaudeCodeCliError, match="is_error=True"):
            _extract_result_text(wrapper)

    def test_empty_stdout_raises(self) -> None:
        with pytest.raises(ClaudeCodeCliError, match="empty stdout"):
            _extract_result_text("")

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(ClaudeCodeCliError, match="not valid JSON"):
            _extract_result_text("not a json")

    def test_missing_result_field_raises(self) -> None:
        wrapper = json.dumps({"type": "result", "is_error": False})
        with pytest.raises(ClaudeCodeCliError, match="missing 'result'"):
            _extract_result_text(wrapper)

    def test_takes_last_nonempty_line(self) -> None:
        stdout = (
            "some debug noise\n"
            + json.dumps({"is_error": False, "result": "ACTUAL"})
            + "\n"
        )
        assert _extract_result_text(stdout) == "ACTUAL"


class TestParseModelJson:
    def test_plain_json(self) -> None:
        assert _parse_model_json('{"a": 1}') == {"a": 1}

    def test_markdown_fenced_json(self) -> None:
        raw = "```json\n{\"a\": 1}\n```"
        assert _parse_model_json(raw) == {"a": 1}

    def test_fenced_without_language(self) -> None:
        raw = "```\n{\"x\": [1, 2]}\n```"
        assert _parse_model_json(raw) == {"x": [1, 2]}


# ---------------------------------------------------------------------------
# Mocked subprocess: complete() end-to-end flow
# ---------------------------------------------------------------------------
class _FakeProcess:
    """Minimal async subprocess stub matching the attributes used."""

    def __init__(
        self,
        *,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int = 0,
        raise_on_communicate: Exception | None = None,  # noqa: ARG002 retained for back-compat
    ):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.kill_called = False

    def communicate(
        self, input: bytes | None = None  # noqa: A002
    ):
        """Return an already-resolved future so tests can create-and-discard
        without triggering 'coroutine never awaited' warnings. The timeout
        test patches ``asyncio.wait_for`` to raise directly; it never awaits
        this future, so we keep it in a clean resolved state."""
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[tuple[bytes, bytes]] = loop.create_future()
        # Always resolve with the recorded bytes; the caller decides whether
        # to read them. Any injected exception manifests via a wait_for patch
        # instead, because that's where timeouts materialize in production.
        fut.set_result((self._stdout, self._stderr))
        return fut

    def kill(self) -> None:
        self.kill_called = True

    async def wait(self) -> int:
        return self.returncode


class TestCompleteFlow:
    @pytest.mark.asyncio
    async def test_successful_call_returns_result(self) -> None:
        client = ClaudeCodeCliClient(_cfg())
        fake = _FakeProcess(
            stdout=json.dumps(
                {"type": "result", "is_error": False, "result": "OK"}
            ).encode()
        )
        with patch(
            "asyncio.create_subprocess_exec",
            AsyncMock(return_value=fake),
        ):
            out = await client.complete(
                tier="haiku",
                system_blocks=[CachedSystemBlock(text="sys")],
                user_message="hi",
            )
        assert out == "OK"

    @pytest.mark.asyncio
    async def test_complete_json_parses_inner_json(self) -> None:
        client = ClaudeCodeCliClient(_cfg())
        fake = _FakeProcess(
            stdout=json.dumps(
                {"type": "result", "is_error": False, "result": '{"k": 42}'}
            ).encode()
        )
        with patch(
            "asyncio.create_subprocess_exec",
            AsyncMock(return_value=fake),
        ):
            out = await client.complete_json(
                tier="sonnet",
                system_blocks=[CachedSystemBlock(text="sys")],
                user_message="hi",
            )
        assert out == {"k": 42}

    @pytest.mark.asyncio
    async def test_nonzero_exit_raises_then_retries_exhaust(self) -> None:
        # Use 1 retry to keep the test quick; tenacity's stop_after_attempt=4
        # would otherwise make this slow.
        client = ClaudeCodeCliClient(_cfg())
        fake = _FakeProcess(stdout=b"", stderr=b"boom", returncode=2)
        with (
            patch(
                "asyncio.create_subprocess_exec", AsyncMock(return_value=fake)
            ),
            patch("zh_ebn_report.clients.claude_code_cli.AsyncRetrying") as retrying,
        ):
            # Make tenacity a single-shot so the test doesn't wait 30s
            async def _single(self_):  # noqa: ANN001
                class _Attempt:
                    def __enter__(self):
                        return self

                    def __exit__(self, exc_type, exc, tb):
                        return False

                yield _Attempt()

            retrying.return_value.__aiter__ = _single
            with pytest.raises(ClaudeCodeCliError, match="exited 2"):
                await client.complete(
                    tier="haiku",
                    system_blocks=[CachedSystemBlock(text="sys")],
                    user_message="hi",
                )

    @pytest.mark.asyncio
    async def test_timeout_kills_subprocess(self) -> None:
        client = ClaudeCodeCliClient(_cfg(), timeout_s=1)
        fake = _FakeProcess()
        with (
            patch(
                "asyncio.create_subprocess_exec", AsyncMock(return_value=fake)
            ),
            patch(
                "asyncio.wait_for",
                AsyncMock(side_effect=TimeoutError()),
            ),
            patch("zh_ebn_report.clients.claude_code_cli.AsyncRetrying") as retrying,
        ):
            async def _single(self_):  # noqa: ANN001
                class _Attempt:
                    def __enter__(self):
                        return self

                    def __exit__(self, exc_type, exc, tb):
                        return False

                yield _Attempt()

            retrying.return_value.__aiter__ = _single
            with pytest.raises(TimeoutError):
                await client.complete(
                    tier="haiku",
                    system_blocks=[CachedSystemBlock(text="sys")],
                    user_message="hi",
                )
        assert fake.kill_called is True


# ---------------------------------------------------------------------------
# Optional: real subprocess sanity check
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    os.getenv("CLAUDE_CODE_INTEGRATION") != "1" or shutil.which("claude") is None,
    reason="integration test; set CLAUDE_CODE_INTEGRATION=1 and install claude CLI",
)
@pytest.mark.asyncio
async def test_integration_real_claude_ping() -> None:
    client = ClaudeCodeCliClient(_cfg(), timeout_s=60)
    out = await client.complete(
        tier="haiku",
        system_blocks=[
            CachedSystemBlock(
                text="You must respond with exactly one word, uppercase."
            )
        ],
        user_message="say hello",
    )
    assert out.strip()
    # Haiku typically replies HELLO or similar; we just need non-empty text.
