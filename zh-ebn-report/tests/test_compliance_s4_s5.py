"""S4 + S5 tests: DOI validation compliance + 摘要 no-citation rule."""

from __future__ import annotations

from zh_ebn_report.models import (
    OxfordLevel,
    Paper,
    Section,
    SectionSelfCheck,
    SourceDB,
    StudyDesign,
)
from zh_ebn_report.pipeline.compliance import (
    _check_abstract_no_citations,
    _check_doi_validation,
)


def _paper(
    doi: str = "10.x/1",
    validated: bool = True,
    metadata_matches: bool | None = True,
) -> Paper:
    return Paper(
        title="Sample title of the article",
        authors=["Author X"],
        year=2024,
        journal="J",
        doi=doi,
        doi_validated=validated,
        doi_metadata_matches=metadata_matches,
        study_design=StudyDesign.RCT,
        oxford_level=OxfordLevel.II,
        source_db=SourceDB.PUBMED,
    )


def _abstract_section(placeholders: list[str]) -> Section:
    return Section(
        section_name="摘要",  # type: ignore[arg-type]
        content_zh="摘要內容……",
        word_count_estimate=10,
        citation_placeholders=placeholders,
        self_check=SectionSelfCheck(
            uses_bi_jia_not_wo=True,
            uses_ge_an_not_bing_ren=True,
            formal_register_only=True,
            cites_phrasing_bank=False,
        ),
    )


class TestDoiValidation:
    def test_validated_paper_passes(self) -> None:
        issues = _check_doi_validation([_paper(validated=True, metadata_matches=True)])
        assert issues == []

    def test_unvalidated_doi_flagged(self) -> None:
        issues = _check_doi_validation(
            [_paper(doi="10.x/fake", validated=False, metadata_matches=None)]
        )
        assert len(issues) == 1
        assert issues[0].rule == "doi_unvalidated"
        assert "10.x/fake" in issues[0].detail

    def test_metadata_mismatch_flagged(self) -> None:
        issues = _check_doi_validation(
            [_paper(doi="10.x/mismatch", validated=True, metadata_matches=False)]
        )
        assert len(issues) == 1
        assert issues[0].rule == "doi_metadata_mismatch"

    def test_metadata_none_tolerated_when_validated(self) -> None:
        # doi_metadata_matches=None means "not checked", acceptable
        issues = _check_doi_validation(
            [_paper(validated=True, metadata_matches=None)]
        )
        assert issues == []


class TestAbstractNoCitations:
    def test_empty_abstract_passes(self) -> None:
        sections = {"摘要": _abstract_section([])}
        assert _check_abstract_no_citations(sections) == []

    def test_citation_in_abstract_flagged(self) -> None:
        sections = {"摘要": _abstract_section(["@smith2024paper", "@doe2023other"])}
        issues = _check_abstract_no_citations(sections)
        assert len(issues) == 1
        assert issues[0].rule == "abstract_no_citations"
        assert "@smith2024paper" in issues[0].detail

    def test_no_abstract_section_is_noop(self) -> None:
        # If 摘要 section is missing altogether, this check returns nothing
        # (a separate missing_section rule handles absence).
        assert _check_abstract_no_citations({}) == []
