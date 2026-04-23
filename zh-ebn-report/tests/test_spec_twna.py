"""Tests for TWNA (台灣護理學會) section spec + per-kind limits."""

from __future__ import annotations

import pytest

from zh_ebn_report.spec import (
    min_references_for,
    page_limit_for,
    section_names,
    section_order,
    total_body_cjk_limit_for,
    word_range_for,
)


class TestSectionOrderDispatch:
    def test_reading_has_8_sections(self) -> None:
        names = section_names("reading")
        assert names == ["摘要", "前言", "主題設定", "搜尋策略", "評讀結果", "綜整", "應用建議", "結論"]

    def test_case_has_7_sections(self) -> None:
        names = section_names("case")
        assert names == ["摘要", "前言", "個案介紹", "方法", "綜整", "應用與評值", "結論"]

    def test_twna_case_has_official_9_chapters(self) -> None:
        """台灣護理學會個案報告送審作業細則：9 章含摘要 + 參考資料（由 CSL 產出）。"""

        names = section_names("twna_case")
        assert names == [
            "摘要",
            "前言",
            "文獻查證",
            "護理評估",
            "問題確立",
            "護理措施",
            "結果評值",
            "討論與結論",
        ]

    def test_twna_project_has_official_10_chapters(self) -> None:
        """TWNA 護理專案送審作業細則：10 章含摘要 + 參考資料（由 CSL 產出）。"""

        names = section_names("twna_project")
        assert names == [
            "摘要",
            "前言",
            "現況分析",
            "問題及導因確立",
            "專案目的",
            "文獻查證",
            "解決辦法及執行過程",
            "結果評值",
            "討論與結論",
        ]

    def test_unknown_kind_raises(self) -> None:
        with pytest.raises(ValueError):
            section_order("nonsense")  # type: ignore[arg-type]


class TestOfficialLimits:
    def test_twna_case_page_limit_is_16(self) -> None:
        assert page_limit_for("twna_case") == 16

    def test_twna_project_page_limit_is_20(self) -> None:
        assert page_limit_for("twna_project") == 20

    def test_twna_case_abstract_cap_500(self) -> None:
        wr = word_range_for("twna_case", "摘要")
        assert wr is not None and wr.max <= 500

    def test_twna_project_abstract_cap_300(self) -> None:
        wr = word_range_for("twna_project", "摘要")
        assert wr is not None and wr.max <= 300

    def test_total_body_limit_matches_pages(self) -> None:
        # TWNA 細則: 每頁 30x20 = 600 CJK chars
        assert total_body_cjk_limit_for("twna_case") == 16 * 600
        assert total_body_cjk_limit_for("twna_project") == 20 * 600

    def test_min_references_project_higher(self) -> None:
        # Nursing project spans more ground; expects more references than case
        assert min_references_for("twna_project") > min_references_for("twna_case")
