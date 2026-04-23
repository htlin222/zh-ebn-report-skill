"""Audit artifact store — complete trail of intermediate products.

Every artifact that crosses a trust boundary (network ↔ us, LLM ↔ us,
guardrail input ↔ guardrail output) is persisted so a reviewer can
reconstruct the entire inference chain months later.

Layout under ``output/<run-id>/artifacts/``::

    _index.jsonl              # append-only log of every artifact
    blobs/
      <sha256>.txt            # content-addressed large payloads
      <sha256>.json           # (system prompts, raw LLM responses…)
    llm/
      <ISO>_<caller>_<tier>_<uuid4>.json
    guardrails/
      <guardrail-name>/
        <ISO>_before.json
        <ISO>_after.json
        <ISO>_diff.json

Content-addressing via SHA-256 is what makes the store cheap even when
every call re-sends a 60 KB system prompt: the prompt body is written
once to ``blobs/<sha>.txt`` and every LLM record just stores the hash.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SHA256_PREFIX_LEN = 12  # keeps filenames short enough for fs listings

# Blob extensions we recognise. Anything else goes to ".bin".
_TEXT_EXTS = {".txt", ".json", ".xml", ".md"}


def _iso_now() -> str:
    """Filesystem-safe ISO timestamp (no colons)."""

    return datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")[:-3]  # ms precision


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class IndexRecord:
    """One line of ``_index.jsonl``. Kept stable for downstream audit tooling."""

    timestamp: str
    category: str  # "llm" | "guardrail" | "network" | "blob"
    name: str
    path: str  # relative to artifacts/ root
    meta: dict[str, Any]


class ArtifactStore:
    """Append-only artifact store for one pipeline run.

    Thread-safe: every write is a single ``open(mode="a" | "w")`` call. We do
    not guarantee ordering across concurrent writers, only durability of each
    individual artifact. The ``_index.jsonl`` uses one line per record so
    partial writes cannot corrupt prior entries.
    """

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "blobs").mkdir(exist_ok=True)
        (self.root / "llm").mkdir(exist_ok=True)
        (self.root / "guardrails").mkdir(exist_ok=True)
        self._index_path = self.root / "_index.jsonl"

    # -----------------------------------------------------------------
    # Blob store (content-addressed dedup)
    # -----------------------------------------------------------------
    def write_blob(self, content: str, *, ext: str = ".txt") -> str:
        """Store ``content`` under ``blobs/<sha256>.ext`` if not already there.

        Returns the full 64-char SHA-256 hex digest. Callers log the hash in
        whatever record references the blob; no duplicate content is written.
        """

        if ext not in _TEXT_EXTS:
            ext = ".bin"
        sha = _sha256_text(content)
        path = self.root / "blobs" / f"{sha}{ext}"
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            self._append_index(
                IndexRecord(
                    timestamp=_iso_now(),
                    category="blob",
                    name=f"{sha[:_SHA256_PREFIX_LEN]}{ext}",
                    path=str(path.relative_to(self.root)),
                    meta={"size_bytes": len(content), "ext": ext},
                )
            )
        return sha

    # -----------------------------------------------------------------
    # LLM call log
    # -----------------------------------------------------------------
    def dump_llm_call(
        self,
        *,
        caller: str,
        tier: str,
        model: str,
        backend: str,
        system_texts: list[str],
        user_message: str,
        response_raw: str,
        response_parsed: Any = None,
        duration_ms: int,
        json_mode: bool,
    ) -> Path:
        """Persist one LLM call. System prompts and user messages go through
        the content-addressed blob store so 30 calls sharing a 60 KB
        knowledge-base prefix take ~60 KB total rather than ~1.8 MB.
        """

        system_hashes = [self.write_blob(s, ext=".txt") for s in system_texts]
        user_hash = self.write_blob(user_message, ext=".txt")
        response_hash = self.write_blob(response_raw, ext=".txt")

        record = {
            "timestamp": _iso_now(),
            "caller": caller,
            "tier": tier,
            "model": model,
            "backend": backend,
            "duration_ms": duration_ms,
            "json_mode": json_mode,
            "system_prompt_sha256": system_hashes,
            "user_message_sha256": user_hash,
            "response_raw_sha256": response_hash,
            "response_parsed": response_parsed,
        }

        name = f"{record['timestamp']}_{caller}_{tier}_{uuid.uuid4().hex[:6]}.json"
        path = self.root / "llm" / name
        path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._append_index(
            IndexRecord(
                timestamp=record["timestamp"],
                category="llm",
                name=name,
                path=str(path.relative_to(self.root)),
                meta={
                    "caller": caller,
                    "tier": tier,
                    "model": model,
                    "backend": backend,
                    "duration_ms": duration_ms,
                },
            )
        )
        return path

    # -----------------------------------------------------------------
    # Guardrail before/after/diff
    # -----------------------------------------------------------------
    def dump_guardrail(
        self,
        name: str,
        *,
        before: Any,
        after: Any,
        summary: Any = None,
    ) -> Path:
        """Persist a guardrail's input state + output state + summary.

        ``before`` / ``after`` must be JSON-serialisable (caller uses
        ``pydantic.BaseModel.model_dump()`` before invoking). ``summary`` can
        be the downgrade list, the correction note, or any audit payload.
        """

        folder = self.root / "guardrails" / name
        folder.mkdir(exist_ok=True)
        ts = _iso_now()
        before_path = folder / f"{ts}_before.json"
        after_path = folder / f"{ts}_after.json"
        summary_path = folder / f"{ts}_summary.json"

        before_path.write_text(
            json.dumps(before, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        after_path.write_text(
            json.dumps(after, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        for kind, path in (
            ("before", before_path),
            ("after", after_path),
            ("summary", summary_path),
        ):
            self._append_index(
                IndexRecord(
                    timestamp=ts,
                    category="guardrail",
                    name=f"{name}/{kind}",
                    path=str(path.relative_to(self.root)),
                    meta={"guardrail": name, "kind": kind},
                )
            )
        return summary_path

    # -----------------------------------------------------------------
    # Index
    # -----------------------------------------------------------------
    def _append_index(self, rec: IndexRecord) -> None:
        line = json.dumps(
            {
                "timestamp": rec.timestamp,
                "category": rec.category,
                "name": rec.name,
                "path": rec.path,
                "meta": rec.meta,
            },
            ensure_ascii=False,
        )
        with self._index_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read_index(self) -> list[dict[str, Any]]:
        """Load the full index for ad-hoc audit queries / tests."""

        if not self._index_path.exists():
            return []
        out: list[dict[str, Any]] = []
        for raw_line in self._index_path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if stripped:
                out.append(json.loads(stripped))
        return out
