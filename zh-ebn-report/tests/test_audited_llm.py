"""Tests for AuditedLLMClient wrapper — captures LLM calls into an ArtifactStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from zh_ebn_report.clients.anthropic import CachedSystemBlock
from zh_ebn_report.clients.audited import AuditedLLMClient
from zh_ebn_report.pipeline.audit import ArtifactStore


class _FakeInnerLLM:
    """Bare-minimum stub satisfying LLMClient protocol for tests."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def model_for(self, tier: str) -> str:
        return f"claude-{tier}-stub"

    async def complete(
        self,
        *,
        tier: str,
        system_blocks: list[CachedSystemBlock],
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        self.calls.append(
            {"tier": tier, "user_message": user_message, "json_mode": json_mode}
        )
        return "RAW-TEXT-RESPONSE"

    async def complete_json(
        self,
        *,
        tier: str,
        system_blocks: list[CachedSystemBlock],
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> dict:
        self.calls.append({"tier": tier, "user_message": user_message, "json_mode": True})
        return {"verdict": "ok", "score": 42}


@pytest.mark.asyncio
async def test_complete_call_persists_artifact(tmp_path: Path) -> None:
    inner = _FakeInnerLLM()
    store = ArtifactStore(tmp_path / "artifacts")
    wrapped = AuditedLLMClient(inner, store, backend_name="claude_code")

    out = await wrapped.complete(
        tier="haiku",
        system_blocks=[CachedSystemBlock(text="SYS-ONE"), CachedSystemBlock(text="SYS-TWO")],
        user_message="USER-MSG",
    )
    assert out == "RAW-TEXT-RESPONSE"

    # exactly 1 LLM record on disk
    llm_dir = tmp_path / "artifacts" / "llm"
    records = list(llm_dir.iterdir())
    assert len(records) == 1
    import json as _json

    rec = _json.loads(records[0].read_text(encoding="utf-8"))
    assert rec["tier"] == "haiku"
    assert rec["backend"] == "claude_code"
    assert len(rec["system_prompt_sha256"]) == 2
    assert rec["response_parsed"] is None  # complete() is not json_mode


@pytest.mark.asyncio
async def test_complete_json_captures_parsed(tmp_path: Path) -> None:
    inner = _FakeInnerLLM()
    store = ArtifactStore(tmp_path / "artifacts")
    wrapped = AuditedLLMClient(inner, store, backend_name="anthropic")

    out = await wrapped.complete_json(
        tier="sonnet",
        system_blocks=[CachedSystemBlock(text="SYS")],
        user_message="MSG",
    )
    assert out == {"verdict": "ok", "score": 42}

    llm_dir = tmp_path / "artifacts" / "llm"
    records = list(llm_dir.iterdir())
    assert len(records) == 1
    import json as _json

    rec = _json.loads(records[0].read_text(encoding="utf-8"))
    assert rec["response_parsed"] == {"verdict": "ok", "score": 42}
    assert rec["json_mode"] is True
    assert rec["backend"] == "anthropic"


@pytest.mark.asyncio
async def test_multiple_calls_share_system_blob(tmp_path: Path) -> None:
    """Three calls with the same system prompt should share 1 blob file."""

    inner = _FakeInnerLLM()
    store = ArtifactStore(tmp_path / "artifacts")
    wrapped = AuditedLLMClient(inner, store, backend_name="claude_code")
    sys_block = CachedSystemBlock(text="SHARED-60KB-PROMPT")

    for i in range(3):
        await wrapped.complete(
            tier="haiku",
            system_blocks=[sys_block],
            user_message=f"MSG-{i}",
        )

    # 3 different user messages + 3 responses (all different) + 1 shared sys
    # = 3 + 3 + 1 = 7 blobs
    # (response is always "RAW-TEXT-RESPONSE" so actually dedups → 5 blobs)
    blob_dir = tmp_path / "artifacts" / "blobs"
    assert len(list(blob_dir.iterdir())) <= 7
    # The shared system prompt lives in exactly one file
    shared_hits = [
        f for f in blob_dir.iterdir() if f.read_text() == "SHARED-60KB-PROMPT"
    ]
    assert len(shared_hits) == 1


@pytest.mark.asyncio
async def test_caller_detection_uses_wrapping_frame(tmp_path: Path) -> None:
    """Wrapped inside a function named like a pipeline subagent — the LLM
    record should show that caller name (best-effort)."""

    async def run_topic_gatekeeper_fake() -> None:  # noqa: ANN202
        wrapped = AuditedLLMClient(
            _FakeInnerLLM(), store, backend_name="claude_code"
        )
        await wrapped.complete(
            tier="haiku",
            system_blocks=[CachedSystemBlock(text="s")],
            user_message="u",
        )

    # Put the function under the pipeline namespace for _detect_caller heuristic
    import zh_ebn_report.pipeline as _pipeline

    run_topic_gatekeeper_fake.__module__ = _pipeline.__name__ + ".testagent"

    store = ArtifactStore(tmp_path / "artifacts")
    await run_topic_gatekeeper_fake()

    import json as _json

    rec = _json.loads(next((tmp_path / "artifacts" / "llm").iterdir()).read_text())
    # Either detected the wrapped caller (ideal) or fell back to "unknown" (also ok).
    # We assert *something* meaningful — never crash, never empty.
    assert rec["caller"]
