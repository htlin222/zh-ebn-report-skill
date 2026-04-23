"""Main driver that chains the 10 subagents through the 5A + 9 CP flow."""

from __future__ import annotations

import logging
from pathlib import Path

from ..clients.anthropic import AnthropicClient
from ..config import AppConfig
from ..models import (
    CaseDetailsDeidentified,
    PipelinePhase,
    ReportType,
    RunState,
    SourceDB,
)
from ..spec import section_names as spec_section_names
from ..state import save_state
from . import agents
from . import checkpoints as cp
from .compliance import (
    ComplianceReport,
    check_sections,
    retry_feedback_for_section,
)
from .evidence_guard import enforce_evidence_levels
from .searcher import run_searches
from .synthesis_guard import normalize_synthesis
from .voice_scan import normalize_voice_result

MAX_COMPLIANCE_RETRIES = 2

log = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, app_cfg: AppConfig, *, auto_yes: bool = False):
        self.app = app_cfg
        self.auto_yes = auto_yes
        self.llm = AnthropicClient(app_cfg.llm)

    # -----------------------------------------------------------------
    # Phase 1: Topic Gatekeeper → CP1
    # -----------------------------------------------------------------
    async def phase_topic(self, state: RunState) -> RunState:
        verdict = await agents.run_topic_gatekeeper(
            llm=self.llm,
            cfg=self.app.pipeline,
            user_topic_raw=state.config.user_topic_raw,
            ward_or_context=state.config.ward_or_context,
            advancement_level=state.config.advancement_level.value,
            report_type=state.config.report_type.value,
        )
        state.topic_verdict = verdict
        state.current_phase = PipelinePhase.TOPIC
        save_state(self.app.pipeline, state)

        choice = cp.prompt(
            self.app.pipeline, state, cp.cp1_summary(state), auto_yes=self.auto_yes
        )
        if choice == "棄題":
            raise RuntimeError("使用者於 CP1 棄題；流程中止")
        if choice == "修改":
            raise RuntimeError("使用者於 CP1 要求修改；請手動調整 topic_verdict 後重跑 phase_pico")
        return state

    # -----------------------------------------------------------------
    # Phase 2: PICO Builder → CP2
    # -----------------------------------------------------------------
    async def phase_pico(self, state: RunState) -> RunState:
        assert state.topic_verdict is not None
        scenario = state.config.clinical_scenario_zh or state.config.ward_or_context
        result = await agents.run_pico_builder(
            llm=self.llm,
            cfg=self.app.pipeline,
            refined_topic_zh=state.topic_verdict.refined_topic_zh,
            refined_topic_en=state.topic_verdict.refined_topic_en,
            clinical_scenario_zh=scenario,
        )
        state.pico_result = result
        state.current_phase = PipelinePhase.PICO
        save_state(self.app.pipeline, state)
        cp.prompt(self.app.pipeline, state, cp.cp2_summary(state), auto_yes=self.auto_yes)
        return state

    # -----------------------------------------------------------------
    # Phase 3: Search Strategist → CP3 → API calls → dedup → DOI valid → CP4
    # -----------------------------------------------------------------
    async def phase_search(
        self, state: RunState, *, manual_imports: dict[SourceDB, Path] | None = None
    ) -> RunState:
        assert state.pico_result is not None
        strategy = await agents.run_search_strategist(
            llm=self.llm,
            cfg=self.app.pipeline,
            pico=state.pico_result.pico,
            year_range_start=state.config.year_range_start,
            year_range_end=state.config.year_range_end,
        )
        # Store a shell SearchResult so CP3 can render strategy
        from ..models import SearchResult

        state.search_result = SearchResult(strategy=strategy, history=[], papers=[])
        save_state(self.app.pipeline, state)
        choice = cp.prompt(
            self.app.pipeline, state, cp.cp3_summary(state), auto_yes=self.auto_yes
        )
        if choice == "重跑":
            raise RuntimeError("使用者於 CP3 要求重跑搜尋策略")

        # Execute the actual searches
        result = await run_searches(
            app_cfg=self.app,
            strategy=strategy,
            manual_imports=manual_imports,
        )
        state.search_result = result
        state.current_phase = PipelinePhase.SEARCH
        save_state(self.app.pipeline, state)

        cp.prompt(self.app.pipeline, state, cp.cp4_summary(state), auto_yes=self.auto_yes)
        return state

    # -----------------------------------------------------------------
    # Phase 4: CASP Appraisers (parallel) → CP5
    # -----------------------------------------------------------------
    async def phase_appraise(self, state: RunState) -> RunState:
        assert state.search_result is not None and state.pico_result is not None
        results = await agents.run_casp_parallel(
            llm=self.llm,
            cfg=self.app.pipeline,
            papers=state.search_result.papers,
            pico=state.pico_result.pico,
            max_concurrency=self.app.pipeline.max_parallel_casp,
        )
        state.casp_results = results

        # Deterministic guardrail: cap Oxford levels against study design
        # (e.g. MA-of-cohort cannot be Level I). Runs before synthesis so the
        # Synthesiser sees normalized evidence levels rather than trusting the
        # per-paper LLM call.
        downgrades = enforce_evidence_levels(
            state.search_result.papers, state.casp_results
        )
        if downgrades:
            log.warning(
                "evidence_guard 套用 %d 筆降級：\n%s",
                len(downgrades),
                "\n".join(d.format() for d in downgrades),
            )
            state.evidence_downgrades = [
                {
                    "paper_doi": d.paper_doi,
                    "paper_title": d.paper_title,
                    "study_design": d.study_design.value,
                    "original_level": d.original_level.value,
                    "corrected_level": d.corrected_level.value,
                    "reason": d.reason,
                }
                for d in downgrades
            ]

        state.current_phase = PipelinePhase.APPRAISE
        save_state(self.app.pipeline, state)
        cp.prompt(self.app.pipeline, state, cp.cp5_summary(state), auto_yes=self.auto_yes)
        return state

    # -----------------------------------------------------------------
    # Phase 5: Synthesiser → CP6
    # -----------------------------------------------------------------
    async def phase_synthesise(self, state: RunState) -> RunState:
        assert state.pico_result is not None and state.search_result is not None
        synth = await agents.run_synthesiser(
            llm=self.llm,
            cfg=self.app.pipeline,
            pico=state.pico_result.pico,
            casp_results=state.casp_results,
            papers=state.search_result.papers,
        )
        # Deterministic guardrail: overwrite the LLM-judged
        # overall_evidence_strength with a Python-derived verdict based on
        # CASP oxford levels + declared contradictions (rule is mechanical
        # per synthesiser.md — no judgment needed).
        synth, note = normalize_synthesis(synth, state.casp_results)
        if note:
            log.warning("synthesis_guard: %s", note)
        state.synthesis = synth
        state.current_phase = PipelinePhase.SYNTHESISE
        save_state(self.app.pipeline, state)
        cp.prompt(self.app.pipeline, state, cp.cp6_summary(state), auto_yes=self.auto_yes)
        return state

    # -----------------------------------------------------------------
    # Phase 5.5 (case only): Case Narrator + Apply Auditor in parallel
    # -----------------------------------------------------------------
    async def phase_case_specifics(
        self,
        state: RunState,
        *,
        case_details: CaseDetailsDeidentified,
        intervention_plan_zh: str,
        pre_observations: list[dict],
        post_observations: list[dict],
        deviations_from_plan: str | None,
    ) -> RunState:
        import asyncio

        assert state.synthesis is not None and state.pico_result is not None
        narrative_task = agents.run_case_narrator(
            llm=self.llm,
            cfg=self.app.pipeline,
            case_details=case_details,
            pico=state.pico_result.pico,
        )
        audit_task = agents.run_apply_auditor(
            llm=self.llm,
            cfg=self.app.pipeline,
            synthesis=state.synthesis,
            intervention_plan_zh=intervention_plan_zh,
            pre_observations=pre_observations,
            post_observations=post_observations,
            deviations_from_plan=deviations_from_plan,
        )
        narrative, audit = await asyncio.gather(narrative_task, audit_task)
        state.case_narrative = narrative
        state.intervention_audit = audit
        save_state(self.app.pipeline, state)
        return state

    # -----------------------------------------------------------------
    # Phase 6: Section Writers (parallel) → compliance loop → CP7
    # -----------------------------------------------------------------
    async def phase_write(self, state: RunState) -> RunState:
        assert state.pico_result is not None and state.synthesis is not None

        kind = state.config.report_type.value  # "reading" | "case" | "twna_case" | "twna_project"
        # 摘要最後寫；其他主章一次並行
        main_section_names = spec_section_names(kind, exclude_abstract=True)

        sections = await agents.run_section_writers_parallel(
            llm=self.llm,
            cfg=self.app.pipeline,
            section_names=main_section_names,
            max_concurrency=self.app.pipeline.max_parallel_sections,
            pico=state.pico_result.pico,
            search_strategy=state.search_result.strategy if state.search_result else None,
            casp_results=state.casp_results,
            papers=state.search_result.papers if state.search_result else None,
            synthesis=state.synthesis,
            case_narrative=state.case_narrative,
            intervention_audit=state.intervention_audit,
            advancement_level=state.config.advancement_level.value,
        )
        abstract = await agents.run_section_writer(
            llm=self.llm,
            cfg=self.app.pipeline,
            section_name="摘要",
            pico=state.pico_result.pico,
            synthesis=state.synthesis,
            other_sections=sections,
            advancement_level=state.config.advancement_level.value,
        )
        state.sections = [abstract, *sections]

        # Programmatic compliance loop — up to N retries for failing sections
        report, retries_used = await self._enforce_compliance(state, kind=kind)
        state.compliance_report = report.to_record(retries_used=retries_used)

        state.current_phase = PipelinePhase.WRITE
        save_state(self.app.pipeline, state)
        cp.prompt(self.app.pipeline, state, cp.cp7_summary(state), auto_yes=self.auto_yes)
        return state

    async def _enforce_compliance(
        self, state: RunState, *, kind: str
    ) -> tuple[ComplianceReport, int]:
        """Re-run failing sections with retry_feedback until spec passes or N retries.

        Returns the final report and the number of retry attempts actually used.
        """

        report = check_sections(state, kind=kind)
        for attempt in range(1, MAX_COMPLIANCE_RETRIES + 1):
            if report.passed:
                return report, attempt - 1
            failing_section_names = sorted(
                {
                    i.section
                    for i in report.errors
                    if i.section in {s.section_name for s in state.sections}
                }
            )
            if not failing_section_names:
                return report, attempt - 1  # title/refs issues can't be rewritten here
            log.info(
                "compliance attempt %d: retrying sections %s",
                attempt,
                failing_section_names,
            )
            await self._retry_sections(state, failing_section_names, report)
            report = check_sections(state, kind=kind)
        return report, MAX_COMPLIANCE_RETRIES

    async def _retry_sections(
        self,
        state: RunState,
        section_names: list[str],
        report: ComplianceReport,
    ) -> None:
        assert state.pico_result is not None and state.synthesis is not None
        rewritten: dict[str, object] = {}
        for name in section_names:
            feedback = retry_feedback_for_section(name, report)
            if feedback is None:
                continue
            # 摘要有特殊 context（其他節草稿）
            other_sections = (
                [s for s in state.sections if s.section_name != "摘要"]
                if name == "摘要"
                else None
            )
            section = await agents.run_section_writer(
                llm=self.llm,
                cfg=self.app.pipeline,
                section_name=name,
                pico=state.pico_result.pico,
                search_strategy=state.search_result.strategy if state.search_result else None,
                casp_results=state.casp_results,
                papers=state.search_result.papers if state.search_result else None,
                synthesis=state.synthesis,
                case_narrative=state.case_narrative,
                intervention_audit=state.intervention_audit,
                advancement_level=state.config.advancement_level.value,
                other_sections=other_sections,
                retry_feedback=feedback,
            )
            rewritten[name] = section
        if rewritten:
            state.sections = [
                rewritten.get(s.section_name, s) for s in state.sections  # type: ignore[misc]
            ]

    # -----------------------------------------------------------------
    # Phase 7: Voice Guard + APA Formatter (parallel) → CP8
    # -----------------------------------------------------------------
    async def phase_check(self, state: RunState) -> RunState:
        import asyncio

        from ..renderers.bibliography import papers_to_bibtex

        assert state.search_result is not None
        full_draft = "\n\n".join(
            f"# {s.section_name}\n\n{s.content_zh}" for s in state.sections
        )
        bib_text = papers_to_bibtex(state.search_result.papers)
        doi_validations = [
            {
                "citekey": p.citekey(),
                "doi": p.doi,
                "doi_resolvable": p.doi_validated,
                "metadata_matches_paper": p.doi_metadata_matches,
                "mismatch_details": None,
            }
            for p in state.search_result.papers
        ]

        voice_task = agents.run_voice_guard(
            llm=self.llm, cfg=self.app.pipeline, full_draft_zh=full_draft
        )
        apa_task = agents.run_apa_formatter(
            llm=self.llm,
            cfg=self.app.pipeline,
            references_bib=bib_text,
            papers=state.search_result.papers,
            doi_validations_json=doi_validations,
        )
        voice, apa = await asyncio.gather(voice_task, apa_task)
        # Regex-based scanner + deterministic pass_threshold recomputation;
        # the LLM's self-reported total_violations / pass_threshold_met are
        # replaced with values derived from the merged violation set.
        voice = normalize_voice_result(voice, full_draft)
        state.voice_check = voice
        state.apa_check = apa
        state.current_phase = PipelinePhase.CHECK
        save_state(self.app.pipeline, state)
        cp.prompt(self.app.pipeline, state, cp.cp8_summary(state), auto_yes=self.auto_yes)
        return state

    # -----------------------------------------------------------------
    # Phase 8: Render → CP9 → final render (so CP9 log enters Appendix D)
    # -----------------------------------------------------------------
    async def phase_render(self, state: RunState) -> RunState:
        from ..renderers.quarto import render_to_docx

        docx_path = render_to_docx(self.app, state)
        state.rendered_docx_path = docx_path
        state.current_phase = PipelinePhase.RENDER
        save_state(self.app.pipeline, state)
        choice = cp.prompt(
            self.app.pipeline, state, cp.cp9_summary(state), auto_yes=self.auto_yes
        )
        # After CP9 is logged, re-render once so Appendix D 含完整的 CP1–CP9 紀錄
        if choice == "確認":
            state.rendered_docx_path = render_to_docx(self.app, state)
            save_state(self.app.pipeline, state)
        return state

    # -----------------------------------------------------------------
    # Full end-to-end
    # -----------------------------------------------------------------
    async def run_reading_full(self, state: RunState) -> RunState:
        state = await self.phase_topic(state)
        state = await self.phase_pico(state)
        state = await self.phase_search(state)
        state = await self.phase_appraise(state)
        state = await self.phase_synthesise(state)
        state = await self.phase_write(state)
        state = await self.phase_check(state)
        state = await self.phase_render(state)
        return state
