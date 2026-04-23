"""S3 tests: overall_evidence_strength is recomputed from CASP levels +
declared contradictions, overriding a lenient or incorrect LLM verdict."""

from __future__ import annotations

from zh_ebn_report.models import (
    CaspItem,
    CaspResult,
    CaspTool,
    Contradiction,
    OxfordLevel,
    SynthesisResult,
)
from zh_ebn_report.pipeline.synthesis_guard import (
    compute_evidence_strength,
    normalize_synthesis,
)


def _casp(doi: str, level: OxfordLevel) -> CaspResult:
    return CaspResult(
        paper_doi=doi,
        tool_used=CaspTool.SR,
        checklist_items=[
            CaspItem(
                q_no=1, question_zh="研究問題是否清楚？", answer="Yes", rationale_zh="明確"
            )
        ],
        validity_zh="合理",
        importance_zh="中",
        applicability_zh="適用",
        oxford_level_2011=level,
    )


def _synth(
    strength: str = "strong",
    contradictions: list[Contradiction] | None = None,
) -> SynthesisResult:
    return SynthesisResult(
        consistency_analysis_zh="整體一致",
        contradictions_zh=contradictions or [],
        overall_evidence_strength=strength,  # type: ignore[arg-type]
        clinical_feasibility_taiwan_zh="可行",
        recommended_intervention_summary_zh="建議 A + B",
        limitations_zh=["樣本小", "單中心", "異質性高"],
    )


class TestComputeEvidenceStrength:
    def test_two_level_i_strong(self) -> None:
        casp = [_casp("10.x/1", OxfordLevel.I), _casp("10.x/2", OxfordLevel.I)]
        assert compute_evidence_strength(casp, contradictions_count=0) == "strong"

    def test_two_level_ii_moderate(self) -> None:
        casp = [_casp("10.x/1", OxfordLevel.II), _casp("10.x/2", OxfordLevel.II)]
        assert compute_evidence_strength(casp, contradictions_count=0) == "moderate"

    def test_one_level_i_plus_one_level_ii_moderate(self) -> None:
        casp = [_casp("10.x/1", OxfordLevel.I), _casp("10.x/2", OxfordLevel.II)]
        # Not enough I's for strong, but I+II ≥ 2 → moderate
        assert compute_evidence_strength(casp, contradictions_count=0) == "moderate"

    def test_level_iii_only_limited(self) -> None:
        casp = [_casp("10.x/1", OxfordLevel.III), _casp("10.x/2", OxfordLevel.III)]
        assert compute_evidence_strength(casp, contradictions_count=0) == "limited"

    def test_contradiction_forces_conflicting(self) -> None:
        # Even with 5 Level I papers, any declared contradiction → conflicting
        casp = [_casp(f"10.x/{i}", OxfordLevel.I) for i in range(5)]
        assert compute_evidence_strength(casp, contradictions_count=1) == "conflicting"


class TestNormalizeSynthesis:
    def test_llm_strong_with_only_level_iii_is_downgraded(self) -> None:
        casp = [_casp("10.x/1", OxfordLevel.III), _casp("10.x/2", OxfordLevel.III)]
        synth = _synth(strength="strong")

        corrected, note = normalize_synthesis(synth, casp)
        assert corrected.overall_evidence_strength == "limited"
        assert note is not None and "strong" in note and "limited" in note

    def test_llm_strong_with_level_i_is_kept(self) -> None:
        casp = [_casp("10.x/1", OxfordLevel.I), _casp("10.x/2", OxfordLevel.I)]
        synth = _synth(strength="strong")

        corrected, note = normalize_synthesis(synth, casp)
        assert corrected.overall_evidence_strength == "strong"
        assert note is None

    def test_llm_ignores_declared_contradiction(self) -> None:
        casp = [_casp("10.x/1", OxfordLevel.I), _casp("10.x/2", OxfordLevel.I)]
        contradiction = Contradiction(
            topic="效果方向不一致",
            paper_a="10.x/1",
            paper_b="10.x/2",
            disagreement="A 顯示降低、B 顯示無差",
            likely_reason="人口差異",
        )
        synth = _synth(strength="strong", contradictions=[contradiction])

        corrected, note = normalize_synthesis(synth, casp)
        assert corrected.overall_evidence_strength == "conflicting"
        assert note is not None
