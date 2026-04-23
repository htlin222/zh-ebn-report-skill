"""Deterministic synthesis-judgment normalizer.

``prompts/synthesiser.md`` encodes a mechanical rule for
``overall_evidence_strength``:

- ``strong``      ↔ ≥2 Oxford Level I papers AND no unresolved contradictions
- ``moderate``    ↔ multiple Level II papers AND no unresolved contradictions
- ``limited``     ↔ mainly Level III–V
- ``conflicting`` ↔ unresolved contradictions present

The LLM was previously trusted to apply this rule to itself. This module
applies it in Python so the verdict is reproducible and auditable.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from ..models import CaspResult, OxfordLevel, SynthesisResult

EvidenceStrength = Literal["strong", "moderate", "limited", "conflicting"]

# Minimum paper counts at each tier to claim the matching verdict.
_MIN_STRONG_LEVEL_I = 2
_MIN_MODERATE_LEVEL_II = 2


def compute_evidence_strength(
    casp_results: list[CaspResult],
    contradictions_count: int,
) -> EvidenceStrength:
    """Derive ``overall_evidence_strength`` from CASP outputs + contradictions.

    Precedence (highest signal wins):
    1. Any unresolved contradictions → ``conflicting``
    2. ≥ _MIN_STRONG_LEVEL_I papers at Level I → ``strong``
    3. ≥ _MIN_MODERATE_LEVEL_II papers at Level II (or combined I+II) → ``moderate``
    4. Otherwise → ``limited``
    """

    if contradictions_count > 0:
        return "conflicting"

    counts = Counter(c.oxford_level_2011 for c in casp_results)
    level_i = counts[OxfordLevel.I]
    level_ii = counts[OxfordLevel.II]

    if level_i >= _MIN_STRONG_LEVEL_I:
        return "strong"
    if level_i + level_ii >= _MIN_MODERATE_LEVEL_II:
        return "moderate"
    return "limited"


def normalize_synthesis(
    synth: SynthesisResult, casp_results: list[CaspResult]
) -> tuple[SynthesisResult, str | None]:
    """Overwrite ``synth.overall_evidence_strength`` with the Python-derived
    verdict. Returns the mutated synth and a human-readable note describing
    the correction (``None`` if nothing changed).

    The LLM's narrative fields (``consistency_analysis_zh`` etc.) are left
    alone — only the categorical verdict is normalized.
    """

    derived = compute_evidence_strength(casp_results, len(synth.contradictions_zh))
    original = synth.overall_evidence_strength
    if derived == original:
        return synth, None

    synth.overall_evidence_strength = derived
    note = (
        f"overall_evidence_strength 由 '{original}' 自動修正為 '{derived}'"
        f"（依 {len(casp_results)} 篇 CASP 結果 + "
        f"{len(synth.contradictions_zh)} 筆矛盾，機械式套用 synthesiser.md 規則）"
    )
    return synth, note
