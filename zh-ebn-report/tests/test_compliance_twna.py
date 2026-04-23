"""Tests for TWNA-specific compliance rules (anonymity, total length)."""

from __future__ import annotations

from datetime import datetime

from zh_ebn_report.models import (
    AdvancementLevel,
    OxfordLevel,
    Paper,
    PipelinePhase,
    ReportType,
    RunConfig,
    RunState,
    Section,
    SectionSelfCheck,
    SourceDB,
    StudyDesign,
)
from zh_ebn_report.pipeline.compliance import check_sections


def _self_check(**overrides: bool) -> SectionSelfCheck:
    defaults = dict(
        uses_bi_jia_not_wo=True,
        uses_ge_an_not_bing_ren=True,
        formal_register_only=True,
        cites_phrasing_bank=True,
    )
    defaults.update(overrides)
    return SectionSelfCheck(**defaults)


def _section(name: str, body: str) -> Section:
    return Section(
        section_name=name,  # type: ignore[arg-type]
        content_zh=body,
        word_count_estimate=len(body),
        citation_placeholders=[],
        self_check=_self_check(),
    )


def _minimal_state(report_type: ReportType) -> RunState:
    cfg = RunConfig(
        run_id="test",
        report_type=report_type,
        advancement_level=AdvancementLevel.N3,
        user_topic_raw="x",
        ward_or_context="x",
        year_range_start=2021,
        year_range_end=2026,
    )
    return RunState(config=cfg, current_phase=PipelinePhase.CHECK)


class TestAnonymity:
    def test_institution_name_flagged(self) -> None:
        state = _minimal_state(ReportType.TWNA_CASE)
        # Add a section with an institution name pattern
        state.sections = [
            _section("前言", "本案例收治於台大醫院外科加護病房，為一位長期臥床之個案。" * 3),
        ]
        report = check_sections(state, kind="twna_case")
        issues = [i for i in report.issues if i.rule == "anonymity_institution"]
        assert issues, f"expected institution issue, got: {[i.rule for i in report.issues]}"

    def test_acknowledgement_flagged(self) -> None:
        state = _minimal_state(ReportType.TWNA_CASE)
        state.sections = [
            _section("結果評值", "感謝指導老師的協助，本照護計畫得以完成。"),
        ]
        report = check_sections(state, kind="twna_case")
        assert any(i.rule == "anonymity_acknowledgement" for i in report.issues)

    def test_personal_title_warning(self) -> None:
        state = _minimal_state(ReportType.TWNA_CASE)
        state.sections = [
            _section("護理措施", "經王醫師評估後給予止痛措施，個案疼痛改善。"),
        ]
        report = check_sections(state, kind="twna_case")
        assert any(i.rule == "anonymity_personal_name" for i in report.issues)

    def test_ebr_reading_does_not_run_anonymity(self) -> None:
        # EBR reading reports don't submit to TWNA; anonymity rule is skipped
        state = _minimal_state(ReportType.EBR_READING)
        state.sections = [
            _section("前言", "本研究於台大醫院進行，感謝指導老師。" * 5),
        ]
        report = check_sections(state, kind="reading")
        assert not any(i.rule.startswith("anonymity_") for i in report.issues)


class TestTotalLength:
    def test_twna_case_over_16_pages_flagged(self) -> None:
        state = _minimal_state(ReportType.TWNA_CASE)
        # 17 pages × 600 chars = 10200 chars (exceeds 9600 cap)
        huge_body = "臨床" * 5100
        state.sections = [
            _section("摘要", "摘要內容" * 50),
            _section("前言", huge_body[:1500]),
            _section("文獻查證", huge_body[:2000]),
            _section("護理評估", huge_body[:2200]),
            _section("護理措施", huge_body[:2800]),
            _section("結果評值", huge_body[:1000]),
            _section("討論與結論", huge_body[:1000]),
        ]
        report = check_sections(state, kind="twna_case")
        assert any(i.rule == "total_length" for i in report.issues)

    def test_twna_project_under_20_pages_passes(self) -> None:
        state = _minimal_state(ReportType.TWNA_PROJECT)
        # Brief sections well under total cap
        state.sections = [_section("摘要", "內容" * 100)]
        report = check_sections(state, kind="twna_project")
        assert not any(i.rule == "total_length" for i in report.issues)


class TestPerKindReferences:
    def _papers(self, n: int, level: OxfordLevel = OxfordLevel.II) -> list[Paper]:
        return [
            Paper(
                title=f"t{i}",
                authors=[f"Author{i} X"],
                year=2025,
                journal="J",
                doi=f"10.x/{i}",
                study_design=StudyDesign.RCT,
                oxford_level=level,
                source_db=SourceDB.PUBMED,
            )
            for i in range(n)
        ]

    def test_project_requires_more_references(self) -> None:
        from zh_ebn_report.pipeline.compliance import _check_references

        # 5 papers fine for twna_case but insufficient for twna_project (min 10)
        issues_case = _check_references(self._papers(5), kind="twna_case")
        issues_proj = _check_references(self._papers(5), kind="twna_project")
        assert not any(i.rule == "min_count" for i in issues_case)
        assert any(i.rule == "min_count" for i in issues_proj)

    def test_twna_case_does_not_enforce_high_level_evidence(self) -> None:
        # TWNA traditional case reports don't require Oxford I-II minimum
        from zh_ebn_report.pipeline.compliance import _check_references

        issues = _check_references(
            self._papers(5, level=OxfordLevel.IV), kind="twna_case"
        )
        assert not any(i.rule == "min_high_level_evidence" for i in issues)

    def test_ebr_reading_still_enforces_high_level(self) -> None:
        from zh_ebn_report.pipeline.compliance import _check_references

        issues = _check_references(
            self._papers(5, level=OxfordLevel.IV), kind="reading"
        )
        assert any(i.rule == "min_high_level_evidence" for i in issues)
