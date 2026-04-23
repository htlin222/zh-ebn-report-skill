"""Tests for ArtifactStore: blob dedup, LLM call dump, guardrail dump, index."""

from __future__ import annotations

import json
from pathlib import Path

from zh_ebn_report.pipeline.audit import ArtifactStore, _sha256_text


class TestBlobDedup:
    def test_write_once_dedupes(self, tmp_path: Path) -> None:
        store = ArtifactStore(tmp_path / "artifacts")
        h1 = store.write_blob("same content", ext=".txt")
        h2 = store.write_blob("same content", ext=".txt")
        assert h1 == h2 == _sha256_text("same content")
        blob_dir = tmp_path / "artifacts" / "blobs"
        assert len(list(blob_dir.iterdir())) == 1

    def test_different_content_different_blobs(self, tmp_path: Path) -> None:
        store = ArtifactStore(tmp_path / "artifacts")
        store.write_blob("a", ext=".txt")
        store.write_blob("b", ext=".txt")
        blob_dir = tmp_path / "artifacts" / "blobs"
        assert len(list(blob_dir.iterdir())) == 2

    def test_unknown_ext_falls_back_to_bin(self, tmp_path: Path) -> None:
        store = ArtifactStore(tmp_path / "artifacts")
        store.write_blob("x", ext=".weird")
        files = list((tmp_path / "artifacts" / "blobs").iterdir())
        assert any(f.suffix == ".bin" for f in files)


class TestDumpLlmCall:
    def test_dump_writes_record_and_blobs(self, tmp_path: Path) -> None:
        store = ArtifactStore(tmp_path / "artifacts")
        path = store.dump_llm_call(
            caller="run_topic_gatekeeper",
            tier="haiku",
            model="claude-haiku-4-5-20251001",
            backend="claude_code",
            system_texts=["big system prompt A", "small system prompt B"],
            user_message="Please refine the topic.",
            response_raw='{"verdict": "feasible"}',
            response_parsed={"verdict": "feasible"},
            duration_ms=1234,
            json_mode=True,
        )
        assert path.exists()
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["caller"] == "run_topic_gatekeeper"
        assert record["tier"] == "haiku"
        assert record["duration_ms"] == 1234
        assert len(record["system_prompt_sha256"]) == 2
        assert record["user_message_sha256"] == _sha256_text("Please refine the topic.")
        assert record["response_parsed"] == {"verdict": "feasible"}
        # Blobs for sys/user/response are all present
        blob_dir = tmp_path / "artifacts" / "blobs"
        blob_files = {f.stem for f in blob_dir.iterdir()}
        assert record["user_message_sha256"] in blob_files
        for sys_sha in record["system_prompt_sha256"]:
            assert sys_sha in blob_files

    def test_repeat_call_reuses_blobs(self, tmp_path: Path) -> None:
        store = ArtifactStore(tmp_path / "artifacts")
        for _ in range(3):
            store.dump_llm_call(
                caller="run_casp_appraiser",
                tier="sonnet",
                model="claude-sonnet-4-6",
                backend="claude_code",
                system_texts=["A", "B"],
                user_message="same",
                response_raw='{"ok": true}',
                duration_ms=10,
                json_mode=True,
            )
        blob_dir = tmp_path / "artifacts" / "blobs"
        # 3 calls × (2 sys + 1 user + 1 resp) = 12 handles but only 4 unique
        assert len(list(blob_dir.iterdir())) == 4


class TestDumpGuardrail:
    def test_before_after_summary_written(self, tmp_path: Path) -> None:
        store = ArtifactStore(tmp_path / "artifacts")
        store.dump_guardrail(
            "evidence_guard",
            before={"papers": [{"doi": "10.x/1", "oxford_level": "I"}]},
            after={"papers": [{"doi": "10.x/1", "oxford_level": "III"}]},
            summary=[{"doi": "10.x/1", "delta": "I→III"}],
        )
        folder = tmp_path / "artifacts" / "guardrails" / "evidence_guard"
        files = sorted(f.name for f in folder.iterdir())
        # three files with the same timestamp prefix
        assert len(files) == 3
        assert any(n.endswith("_before.json") for n in files)
        assert any(n.endswith("_after.json") for n in files)
        assert any(n.endswith("_summary.json") for n in files)


class TestIndex:
    def test_each_artifact_records_an_index_line(self, tmp_path: Path) -> None:
        store = ArtifactStore(tmp_path / "artifacts")
        store.write_blob("x", ext=".txt")
        store.dump_llm_call(
            caller="c",
            tier="haiku",
            model="m",
            backend="claude_code",
            system_texts=["s"],
            user_message="u",
            response_raw="r",
            duration_ms=1,
            json_mode=False,
        )
        store.dump_guardrail(
            "voice_scan",
            before={"v": 0},
            after={"v": 5},
            summary={"delta": 5},
        )
        idx = store.read_index()
        categories = [r["category"] for r in idx]
        assert "blob" in categories
        assert "llm" in categories
        assert "guardrail" in categories
        # Each entry has timestamp + path + meta
        for rec in idx:
            assert rec["timestamp"]
            assert rec["path"]
            assert "meta" in rec

    def test_index_is_append_only(self, tmp_path: Path) -> None:
        """Re-opening the store must not truncate or rewrite the index."""
        store1 = ArtifactStore(tmp_path / "artifacts")
        store1.write_blob("first", ext=".txt")
        initial = store1.read_index()
        store2 = ArtifactStore(tmp_path / "artifacts")
        store2.write_blob("second", ext=".txt")
        combined = store2.read_index()
        assert len(combined) == len(initial) + 1
