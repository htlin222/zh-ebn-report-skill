"""Deterministic voice-guard scanner.

The LLM-based Voice Guard (Haiku) previously reported its own violations
*and* its own ``pass_threshold_met`` verdict — a self-discipline loop that
misses violations when the LLM is lenient. This module runs a regex-based
scanner over the draft, emits ``VoiceViolation`` records, and then recomputes
``pass_threshold_met`` from the merged (LLM ∪ regex) violation list using
the rules declared in ``prompts/voice_guard.md``.

Banned tokens are sourced from ``prompts/_base.md`` and ``prompts/voice_guard.md``.
Misses (false negatives) are worse than false positives here — violations
are reviewable, whereas skipped violations silently ship.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..models import VoiceCheckResult, VoiceViolation

# Category → list of (pattern, severity). Patterns are unicode literals, used
# via ``re.compile(pattern)``. When editing, keep them tight enough to avoid
# matching inside legitimate phrases — e.g. ``我`` is matched only when it is
# not part of ``我國`` / ``自我`` / ``我方`` (those are whitelisted).
_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "第一人稱誤用": [
        # Standalone 我 / 我們 / 本人; exclude 我國/自我/我方/我院 etc.
        (r"(?<![一-鿿])我(?![國方院們])", "high"),
        (r"我們", "high"),
        (r"本人", "high"),
    ],
    "病患稱謂錯誤": [
        (r"病人", "high"),
        (r"患者", "high"),
        (r"病患", "high"),
    ],
    "口語化": [
        # sentence-final particles: only when followed by punctuation or EOL,
        # so we do not match legitimate compounds like 了解 / 了如指掌
        (r"[了啦耶吧](?=[。！？；，、\s]|$)", "medium"),
        (r"覺得", "medium"),
        (r"想說", "medium"),
        (r"就是(?![這那如])", "medium"),
        (r"好幾個", "medium"),
        (r"幾十篇", "medium"),
    ],
    "動詞非書面語": [
        # 找 as a standalone verb is surprisingly rare in formal writing; the
        # primary offenders in draft corpora are 我找/去找/就找, so we bias
        # toward those contexts rather than any ``找``.
        (r"(?:去|就|再|先|後|才)找(?![到出])", "medium"),
    ],
    "含糊語言": [
        (r"大致上", "high"),
        (r"基本上", "high"),
        (r"差不多", "high"),
        (r"應該是", "high"),
        (r"似乎", "high"),
        (r"可能有", "high"),
    ],
}

# Threshold rule from prompts/voice_guard.md §pass_threshold_met:
#   pass = (high_count == 0) AND (medium_count <= 3)
_MAX_MEDIUM = 3


def _scan_category(
    text: str, category: str, patterns: list[tuple[str, str]]
) -> list[VoiceViolation]:
    """Emit one ``VoiceViolation`` per regex hit, with a short excerpt."""

    violations: list[VoiceViolation] = []
    for pattern, severity in patterns:
        for m in re.finditer(pattern, text):
            start = max(0, m.start() - 10)
            end = min(len(text), m.end() + 10)
            excerpt = text[start:end].replace("\n", " ").strip()
            violations.append(
                VoiceViolation(
                    category=category,  # type: ignore[arg-type]
                    location_excerpt=excerpt,
                    suggested_rewrite=_suggest_rewrite(category, m.group()),
                    severity=severity,  # type: ignore[arg-type]
                )
            )
    return violations


def _suggest_rewrite(category: str, hit: str) -> str:
    """Canned rewrite hints. Good enough for a reviewer to act on; no NLP."""

    if category == "第一人稱誤用":
        return "改為『筆者』或採用被動句／去主詞句"
    if category == "病患稱謂錯誤":
        return "改為『個案』或『案○』（案母／案父等）"
    if category == "口語化":
        return "改為書面語；刪除語尾虛詞或替換具體用語"
    if category == "動詞非書面語":
        return "改為『檢索』『運用』『指出』『提供』等書面動詞"
    if category == "含糊語言":
        return f"刪除『{hit}』或改為帶數值／具體依據的描述"
    return "請改寫為符合護理實證報告語氣的句式"


def scan_draft(full_draft_zh: str) -> list[VoiceViolation]:
    """Run every category scan over the draft.

    Returns a flat list of violations. Order matches the order of
    ``_PATTERNS`` (category-major, then textual order of hits).
    """

    all_violations: list[VoiceViolation] = []
    for category, patterns in _PATTERNS.items():
        all_violations.extend(_scan_category(full_draft_zh, category, patterns))
    return all_violations


def _violation_key(v: VoiceViolation) -> tuple[str, str, str]:
    """Deduplication key: same category + same offending excerpt = duplicate."""

    return (v.category, v.location_excerpt, v.severity)


def merge_violations(
    llm_violations: Iterable[VoiceViolation],
    regex_violations: Iterable[VoiceViolation],
) -> list[VoiceViolation]:
    """Union two violation sets, dedup by (category, excerpt, severity).

    LLM output is kept on ties so its ``suggested_rewrite`` wording survives
    — the LLM produces more contextual rewrites than the canned hints here.
    """

    seen: dict[tuple[str, str, str], VoiceViolation] = {}
    for v in llm_violations:
        seen[_violation_key(v)] = v
    for v in regex_violations:
        seen.setdefault(_violation_key(v), v)
    return list(seen.values())


def recompute_pass_threshold(violations: list[VoiceViolation]) -> bool:
    """Evaluate ``prompts/voice_guard.md``'s pass rule in Python.

    Rule: pass ↔ no ``high`` severity AND ≤3 ``medium`` severity.
    """

    high = sum(1 for v in violations if v.severity == "high")
    medium = sum(1 for v in violations if v.severity == "medium")
    return high == 0 and medium <= _MAX_MEDIUM


def normalize_voice_result(
    llm_result: VoiceCheckResult, full_draft_zh: str
) -> VoiceCheckResult:
    """Merge LLM-reported violations with regex scan, recompute pass verdict.

    The returned ``VoiceCheckResult`` replaces the LLM's self-reported
    ``total_violations`` and ``pass_threshold_met`` with values derived
    from the merged violation set.
    """

    regex_violations = scan_draft(full_draft_zh)
    merged = merge_violations(llm_result.violations, regex_violations)
    return VoiceCheckResult(
        violations=merged,
        total_violations=len(merged),
        pass_threshold_met=recompute_pass_threshold(merged),
    )
