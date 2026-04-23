"""S1+S2 tests: regex scanner catches violations the LLM missed, and
``pass_threshold_met`` is recomputed deterministically from the merged set."""

from __future__ import annotations

from zh_ebn_report.models import VoiceCheckResult, VoiceViolation
from zh_ebn_report.pipeline.voice_scan import (
    merge_violations,
    normalize_voice_result,
    recompute_pass_threshold,
    scan_draft,
)


class TestScanDraft:
    def test_first_person_caught(self) -> None:
        violations = scan_draft("我認為此介入有效。我們收集了資料。")
        cats = [v.category for v in violations]
        assert "第一人稱誤用" in cats
        assert len([c for c in cats if c == "第一人稱誤用"]) >= 2

    def test_patient_appellation_caught(self) -> None:
        violations = scan_draft("病人入院當天進行評估，患者表示疼痛。")
        assert any(v.category == "病患稱謂錯誤" and v.severity == "high" for v in violations)

    def test_vague_language_caught(self) -> None:
        violations = scan_draft("似乎有效；大致上改善；應該是可行。")
        cats = [v.category for v in violations if v.severity == "high"]
        assert cats.count("含糊語言") >= 3

    def test_whitelist_prevents_false_positive_for_wo_guo(self) -> None:
        # 我國 / 自我 / 我院 should NOT match 第一人稱誤用
        violations = scan_draft("我國醫療體系強調自我照護能力，我院亦然。")
        first_person_hits = [v for v in violations if v.category == "第一人稱誤用"]
        assert first_person_hits == [], (
            f"false positive on 我國/自我/我院: {[v.location_excerpt for v in first_person_hits]}"
        )

    def test_le_character_not_matched_in_compound(self) -> None:
        # 了解 / 了如指掌 should not trigger 口語化
        violations = scan_draft("護理師了解個案狀況，觀察了如指掌。")
        colloquial = [v for v in violations if v.category == "口語化"]
        assert colloquial == [], (
            f"false positive on 了解/了如指掌: {[v.location_excerpt for v in colloquial]}"
        )

    def test_le_at_sentence_end_matches(self) -> None:
        # 了 / 啦 at end of clause SHOULD match
        violations = scan_draft("介入完成了。效果出來啦！")
        assert any(
            v.category == "口語化" and v.severity == "medium" for v in violations
        )


class TestRecomputePassThreshold:
    def _v(self, severity: str) -> VoiceViolation:
        return VoiceViolation(
            category="含糊語言",  # type: ignore[arg-type]
            location_excerpt="…",
            suggested_rewrite="…",
            severity=severity,  # type: ignore[arg-type]
        )

    def test_zero_violations_passes(self) -> None:
        assert recompute_pass_threshold([]) is True

    def test_any_high_fails(self) -> None:
        assert recompute_pass_threshold([self._v("high")]) is False

    def test_three_mediums_passes(self) -> None:
        assert recompute_pass_threshold([self._v("medium")] * 3) is True

    def test_four_mediums_fails(self) -> None:
        assert recompute_pass_threshold([self._v("medium")] * 4) is False

    def test_many_lows_passes(self) -> None:
        assert recompute_pass_threshold([self._v("low")] * 10) is True


class TestMergeAndNormalize:
    def test_llm_and_regex_are_unioned(self) -> None:
        llm_v = VoiceViolation(
            category="口語化",  # type: ignore[arg-type]
            location_excerpt="覺得不太好",
            suggested_rewrite="改為具體描述",
            severity="medium",  # type: ignore[arg-type]
        )
        regex_v = VoiceViolation(
            category="含糊語言",  # type: ignore[arg-type]
            location_excerpt="…似乎有效…",
            suggested_rewrite="刪除",
            severity="high",  # type: ignore[arg-type]
        )
        merged = merge_violations([llm_v], [regex_v])
        assert len(merged) == 2

    def test_normalize_overrides_lenient_llm_verdict(self) -> None:
        """LLM says pass=True with zero violations; regex finds a high
        violation. Normalized result must flip pass to False."""

        llm_result = VoiceCheckResult(
            violations=[],
            total_violations=0,
            pass_threshold_met=True,
        )
        draft = "本研究似乎顯示顯著改善。"  # 含糊語言 → high
        normalized = normalize_voice_result(llm_result, draft)

        assert normalized.pass_threshold_met is False
        assert normalized.total_violations >= 1
        assert any(v.severity == "high" for v in normalized.violations)

    def test_clean_draft_keeps_pass(self) -> None:
        llm_result = VoiceCheckResult(
            violations=[],
            total_violations=0,
            pass_threshold_met=True,
        )
        draft = "筆者運用 CASP 檢核表進行評讀，個案於術後第三日轉出。"
        normalized = normalize_voice_result(llm_result, draft)
        assert normalized.pass_threshold_met is True
        assert normalized.total_violations == 0
