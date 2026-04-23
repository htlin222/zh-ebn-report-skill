"""Tests for M1–M7: the mid-tier prompt-vs-code enforcement gaps."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from zh_ebn_report.models import (
    CaseNarrative,
    DirectQuote,
    InterventionAudit,
    SixPieceStrategy,
    SynthesisResult,
)
from zh_ebn_report.pipeline.agents import _derive_too_perfect


# ---------------------------------------------------------------------------
# M1: limitations_zh must have at least 3 entries
# ---------------------------------------------------------------------------
class TestLimitationsMinThree:
    def _synth_kwargs(self, limitations: list[str]) -> dict:
        return dict(
            consistency_analysis_zh="一致",
            contradictions_zh=[],
            overall_evidence_strength="moderate",
            clinical_feasibility_taiwan_zh="可行",
            recommended_intervention_summary_zh="X + Y",
            limitations_zh=limitations,
        )

    def test_three_limitations_accepted(self) -> None:
        SynthesisResult(**self._synth_kwargs(["a", "b", "c"]))

    def test_two_limitations_rejected(self) -> None:
        with pytest.raises(ValidationError, match="至少 3 條"):
            SynthesisResult(**self._synth_kwargs(["a", "b"]))

    def test_blank_entries_not_counted(self) -> None:
        # 3 entries but 2 are whitespace-only → should fail
        with pytest.raises(ValidationError, match="至少 3 條"):
            SynthesisResult(**self._synth_kwargs(["real limitation", "   ", ""]))


# ---------------------------------------------------------------------------
# M2: direct_quotes must include both 個案 and 家屬
# ---------------------------------------------------------------------------
class TestDirectQuotesStructure:
    def _narrative_kwargs(self, quotes: list[DirectQuote]) -> dict:
        return dict(
            case_introduction_section_zh="…",
            diagnostic_reasoning_section_zh="…",
            deid_check_passed=True,
            direct_quotes=quotes,
        )

    def test_case_and_family_quote_accepted(self) -> None:
        CaseNarrative(
            **self._narrative_kwargs(
                [
                    DirectQuote(speaker="個案", quote_zh="我覺得傷口好多了"),
                    DirectQuote(speaker="家屬", quote_zh="比起上週進步很多"),
                ]
            )
        )

    def test_only_case_quote_rejected(self) -> None:
        with pytest.raises(ValidationError, match="家屬"):
            CaseNarrative(
                **self._narrative_kwargs(
                    [DirectQuote(speaker="個案", quote_zh="還好")]
                )
            )

    def test_only_family_quote_rejected(self) -> None:
        with pytest.raises(ValidationError, match="個案"):
            CaseNarrative(
                **self._narrative_kwargs(
                    [DirectQuote(speaker="家屬", quote_zh="進步很多")]
                )
            )


# ---------------------------------------------------------------------------
# M3: time_stamped_table ≥ 2 rows with required keys
# ---------------------------------------------------------------------------
class TestTimeStampedTable:
    def _audit_kwargs(self, table: list[dict[str, str]]) -> dict:
        return dict(
            apply_section_zh="…",
            audit_section_zh="…",
            time_stamped_table=table,
            deviation_explanation_zh=None,
            warning_too_perfect=False,
        )

    def test_two_rows_with_english_keys(self) -> None:
        InterventionAudit(
            **self._audit_kwargs(
                [
                    {"timestamp": "Day 1", "scale": "Braden", "value": "14"},
                    {"timestamp": "Day 7", "scale": "Braden", "value": "19"},
                ]
            )
        )

    def test_two_rows_with_chinese_keys(self) -> None:
        InterventionAudit(
            **self._audit_kwargs(
                [
                    {"時間": "第 1 日", "量表": "Braden", "數值": "14"},
                    {"時間": "第 7 日", "量表": "Braden", "數值": "19"},
                ]
            )
        )

    def test_one_row_rejected(self) -> None:
        with pytest.raises(ValidationError, match="至少需要 2 筆"):
            InterventionAudit(
                **self._audit_kwargs(
                    [{"timestamp": "Day 1", "scale": "X", "value": "0"}]
                )
            )

    def test_missing_value_key_rejected(self) -> None:
        with pytest.raises(ValidationError, match="缺少必要欄位"):
            InterventionAudit(
                **self._audit_kwargs(
                    [
                        {"timestamp": "Day 1", "scale": "X"},
                        {"timestamp": "Day 7", "scale": "X"},
                    ]
                )
            )


# ---------------------------------------------------------------------------
# M4 + M5: case-privacy scan + absolute-language scan
# ---------------------------------------------------------------------------
class TestComplianceM4M5:
    def _section(self, name: str, body: str):
        from zh_ebn_report.models import Section, SectionSelfCheck

        return Section(
            section_name=name,  # type: ignore[arg-type]
            content_zh=body,
            word_count_estimate=len(body),
            citation_placeholders=[],
            self_check=SectionSelfCheck(
                uses_bi_jia_not_wo=True,
                uses_ge_an_not_bing_ren=True,
                formal_register_only=True,
                cites_phrasing_bank=False,
            ),
        )

    def test_specific_age_flagged(self) -> None:
        from zh_ebn_report.pipeline.compliance import _check_case_privacy

        sections = {"個案介紹": self._section("個案介紹", "個案為 42 歲男性，主訴胸痛。")}
        issues = _check_case_privacy(sections)
        assert any(i.rule == "case_privacy_specific_age" for i in issues)

    def test_age_range_allowed(self) -> None:
        from zh_ebn_report.pipeline.compliance import _check_case_privacy

        sections = {
            "個案介紹": self._section("個案介紹", "個案為 40–50 歲男性，主訴胸痛。")
        }
        issues = _check_case_privacy(sections)
        assert not any(i.rule == "case_privacy_specific_age" for i in issues)

    def test_occupation_flagged(self) -> None:
        from zh_ebn_report.pipeline.compliance import _check_case_privacy

        sections = {
            "個案介紹": self._section(
                "個案介紹", "個案為 40–50 歲，職業為工程師，入院前長期加班。"
            )
        }
        issues = _check_case_privacy(sections)
        assert any(i.rule == "case_privacy_occupation" for i in issues)

    def test_absolute_language_flagged_in_conclusion(self) -> None:
        from zh_ebn_report.pipeline.compliance import _check_absolute_language

        sections = {
            "結論": self._section("結論", "本介入應全面推廣於所有病房。"),
        }
        issues = _check_absolute_language(sections)
        assert any(i.rule == "absolute_language" for i in issues)
        # Both "全面推廣" AND "所有病房" should be detected
        assert len([i for i in issues if i.rule == "absolute_language"]) == 2

    def test_absolute_language_not_triggered_by_normal_prose(self) -> None:
        from zh_ebn_report.pipeline.compliance import _check_absolute_language

        sections = {
            "應用建議": self._section(
                "應用建議", "建議於內科病房先行試辦，依成效再擴展至其他單位。"
            ),
        }
        assert _check_absolute_language(sections) == []


# ---------------------------------------------------------------------------
# M6: Boolean query must not have > 3 OR in any single parenthesized cluster
# ---------------------------------------------------------------------------
class TestBooleanOrLimit:
    def _strategy_kwargs(self, pubmed: str) -> dict:
        return dict(
            primary_terms=["a", "b", "c"],
            synonyms=["s1", "s2", "s3", "s4", "s5"],
            mesh_terms=["Humans"],
            cinahl_headings=["MH"],
            boolean_query_pubmed=pubmed,
            boolean_query_cochrane="(a OR b)",
            boolean_query_cinahl="(a OR b)",
            field_codes_used={"title": "[Title]"},
        )

    def test_three_ors_in_cluster_accepted(self) -> None:
        # (a OR b OR c OR d) = 3 OR, 4 terms = OK
        SixPieceStrategy(**self._strategy_kwargs("(a OR b OR c OR d) AND humans"))

    def test_four_ors_in_cluster_rejected(self) -> None:
        # (a OR b OR c OR d OR e) = 4 OR, 5 terms → should fail
        with pytest.raises(ValidationError, match="OR-連接自由字群"):
            SixPieceStrategy(
                **self._strategy_kwargs("(a OR b OR c OR d OR e) AND humans")
            )


# ---------------------------------------------------------------------------
# M7: warning_too_perfect derivation
# ---------------------------------------------------------------------------
class TestWarningTooPerfect:
    def test_identical_pre_post_triggers_warning(self) -> None:
        pre = [{"scale": "Braden", "value": "18"}]
        post = [{"scale": "Braden", "value": "18"}]
        assert _derive_too_perfect(pre, post) is True

    def test_all_post_at_extreme_triggers_warning(self) -> None:
        pre = [{"scale": "compliance", "value": "60"}]
        post = [{"scale": "compliance", "value": "100"}]
        assert _derive_too_perfect(pre, post) is True

    def test_normal_improvement_no_warning(self) -> None:
        pre = [{"scale": "Braden", "value": "14"}]
        post = [{"scale": "Braden", "value": "19"}]
        assert _derive_too_perfect(pre, post) is False

    def test_empty_post_no_warning(self) -> None:
        # No post data yet → don't falsely warn
        assert _derive_too_perfect([{"scale": "X", "value": "1"}], []) is False
