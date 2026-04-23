"""Runtime configuration loaded from .env / environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class LlmConfig:
    """Backend-agnostic LLM configuration.

    Resolution order:
    1. ``LLM_BACKEND=claude_code`` (default) — shell out to ``claude -p`` CLI;
       uses the user's Claude subscription, no API key required.
    2. ``LLM_BACKEND=anthropic`` — direct Anthropic SDK; requires
       ``ANTHROPIC_API_KEY`` (or ``LLM_API_KEY``) + optional ``LLM_API_BASE``
       for proxies.
    3. ``LLM_BACKEND=auto`` — prefer ``claude_code`` when ``claude`` binary is
       on PATH, else fall back to ``anthropic``.
    """

    backend: str
    api_key: str
    base_url: str | None
    default_model: str
    haiku_model: str
    sonnet_model: str
    opus_model: str

    @classmethod
    def from_env(cls) -> LlmConfig:
        backend = os.getenv("LLM_BACKEND", "claude_code").lower()
        key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("LLM_API_KEY", "")
        base = os.getenv("ANTHROPIC_BASE_URL") or os.getenv("LLM_API_BASE") or None
        default = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
        # Model IDs for the SDK backend. The CLI backend uses aliases like
        # "haiku"/"sonnet"/"opus" natively, but also accepts full IDs.
        return cls(
            backend=backend,
            api_key=key,
            base_url=base,
            default_model=default,
            haiku_model=os.getenv("LLM_MODEL_HAIKU", "claude-haiku-4-5-20251001"),
            sonnet_model=os.getenv("LLM_MODEL_SONNET", "claude-sonnet-4-6"),
            opus_model=os.getenv("LLM_MODEL_OPUS", "claude-opus-4-7"),
        )


@dataclass(frozen=True)
class DatabaseKeys:
    pubmed: str | None
    scopus: str | None
    scopus_inst_token: str | None
    embase: str | None
    embase_inst_token: str | None
    embase_auth_token: str | None
    crossref_mailto: str | None
    unpaywall_email: str | None

    @classmethod
    def from_env(cls) -> DatabaseKeys:
        return cls(
            pubmed=os.getenv("PUBMED_API_KEY") or None,
            scopus=os.getenv("SCOPUS_API_KEY") or None,
            scopus_inst_token=os.getenv("SCOPUS_INST_TOKEN") or None,
            embase=os.getenv("EMBASE_API_KEY") or None,
            embase_inst_token=os.getenv("EMBASE_INST_TOKEN") or None,
            embase_auth_token=os.getenv("EMBASE_AUTH_TOKEN") or None,
            crossref_mailto=(
                os.getenv("CROSSREF_MAILTO")
                or os.getenv("UNPAYWALL_EMAIL")
                or None
            ),
            unpaywall_email=os.getenv("UNPAYWALL_EMAIL") or None,
        )


@dataclass(frozen=True)
class PipelineConfig:
    max_parallel_casp: int
    max_parallel_sections: int
    default_year_range: int
    output_root: Path
    skill_root: Path

    @classmethod
    def from_env(cls) -> PipelineConfig:
        return cls(
            max_parallel_casp=int(os.getenv("MAX_PARALLEL_CASP_APPRAISERS", "8")),
            max_parallel_sections=int(os.getenv("MAX_PARALLEL_SECTION_WRITERS", "6")),
            default_year_range=int(os.getenv("DEFAULT_TARGET_YEAR_RANGE", "5")),
            output_root=_PROJECT_ROOT / "output",
            skill_root=_PROJECT_ROOT / "zh-ebn-report",
        )


@dataclass(frozen=True)
class AppConfig:
    llm: LlmConfig
    dbs: DatabaseKeys
    pipeline: PipelineConfig

    @classmethod
    def load(cls) -> AppConfig:
        return cls(
            llm=LlmConfig.from_env(),
            dbs=DatabaseKeys.from_env(),
            pipeline=PipelineConfig.from_env(),
        )


def project_root() -> Path:
    return _PROJECT_ROOT
