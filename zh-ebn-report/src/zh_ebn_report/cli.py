"""Typer CLI entry point.

Commands:
- init      Create a new run directory.
- run       End-to-end pipeline (or resume from current phase).
- topic     Run only Phase 1.
- pico      Run only Phase 2.
- search    Run only Phase 3.
- appraise  Run only Phase 4.
- synthesise  Run only Phase 5.
- write     Run only Phase 6.
- check     Run only Phase 7.
- render    Run only Phase 8 (DRAFT DOCX).
- status    Show the current phase + checkpoint log.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import AppConfig
from .models import (
    AdvancementLevel,
    PipelinePhase,
    ReportType,
    RunConfig,
    SourceDB,
)
from .pipeline.orchestrator import Orchestrator
from .state import init_state, load_state, new_run_id

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

console = Console()
app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="台灣護理實證報告自動化 AI 協作 Pipeline",
)

# Register `tools` subcommand group — pure utilities for Claude Code mode
# (no LLM call inside Python; LLM work happens via Agent tool dispatch).
from .cli_tools import tools_app  # noqa: E402
app.add_typer(tools_app, name="tools", help="Claude Code 模式下可呼叫的 utility 命令（PubMed / CrossRef / deid / dedup / state）")


def _ethics_guard(flag: bool) -> None:
    if not flag:
        console.print(
            "[bold red]錯誤：[/]必須傳 --i-accept-audit-responsibility 旗標才能執行。\n"
            "此旗標代表你承諾：\n"
            " 1. 逐節審閱與修訂 AI 產出之內容\n"
            " 2. 對本文內容的真實性與準確性承擔全部責任\n"
            " 3. 在送審文件中附上 AI 使用揭露段落\n"
            "（依台灣護理學會《生成式 AI 使用規範》）"
        )
        raise typer.Exit(2)


def _load_cfg() -> AppConfig:
    cfg = AppConfig.load()
    backend = cfg.llm.backend
    if backend == "auto":
        backend = "claude_code" if shutil.which("claude") else "anthropic"
    if backend == "anthropic" and not cfg.llm.api_key:
        console.print(
            "[red]錯誤：LLM_BACKEND=anthropic 需 ANTHROPIC_API_KEY。[/]\n"
            "改設 [cyan]LLM_BACKEND=claude_code[/] 走訂閱（預設），"
            "並確認 `which claude` 有值。"
        )
        raise typer.Exit(2)
    if backend == "claude_code" and shutil.which("claude") is None:
        console.print(
            "[red]錯誤：PATH 上找不到 `claude` CLI。[/]\n"
            "請安裝 Claude Code，或改設 LLM_BACKEND=anthropic + ANTHROPIC_API_KEY。"
        )
        raise typer.Exit(2)
    return cfg


@app.command()
def init(
    type_: Annotated[
        ReportType,
        typer.Option(
            "--type",
            help=(
                "reading (EBR 讀書報告 N1/N2) | case (EBR 案例分析 N3 TEBNA) | "
                "twna_case (TWNA 個案報告 N2/N3) | twna_project (TWNA 護理專案 N4)"
            ),
        ),
    ],
    topic: Annotated[str, typer.Option("--topic", help="糊的題目也可以；守門員會幫你細化")],
    ward: Annotated[str, typer.Option("--ward", help="病房別或臨床情境")] = "一般病房",
    level: Annotated[
        AdvancementLevel, typer.Option("--level", help="N1/N2/N3/N4")
    ] = AdvancementLevel.N2,
    year_range: Annotated[int, typer.Option("--year-range", help="近 N 年")] = 5,
    scenario: Annotated[str, typer.Option("--scenario", help="1-2 段臨床情境說明")] = "",
    case_file: Annotated[
        Optional[Path],
        typer.Option("--case-file", help="案例分析必填；YAML 格式的去識別化個案資料"),
    ] = None,
    accept: Annotated[
        bool,
        typer.Option(
            "--i-accept-audit-responsibility",
            help="必填旗標：承諾人類 audit 與責任",
        ),
    ] = False,
) -> None:
    """初始化一個新的 run 並寫入 output/<run-id>/state.json。"""

    _ethics_guard(accept)
    cfg = _load_cfg()

    if type_ in (ReportType.EBR_CASE, ReportType.TWNA_CASE) and case_file is None:
        console.print("[red]錯誤：案例分析／個案報告必須提供 --case-file（去識別化 YAML）[/]")
        raise typer.Exit(2)

    now_year = datetime.utcnow().year
    config = RunConfig(
        run_id=new_run_id(),
        report_type=type_,
        advancement_level=level,
        user_topic_raw=topic,
        ward_or_context=ward,
        clinical_scenario_zh=scenario or None,
        case_file_path=case_file,
        target_databases=[
            SourceDB.PUBMED,
            SourceDB.SCOPUS,
            SourceDB.EMBASE,
            SourceDB.COCHRANE,
            SourceDB.CINAHL,
            SourceDB.AIRITI,
        ],
        year_range_start=now_year - year_range,
        year_range_end=now_year,
    )
    state = init_state(cfg.pipeline, config)
    console.print(
        f"[green]✓[/] 已建立 run：[bold]{state.config.run_id}[/]\n"
        f"路徑：{cfg.pipeline.output_root / state.config.run_id}"
    )


def _orch_run(phase_fn_name: str, run_id: str, auto_yes: bool) -> None:
    cfg = _load_cfg()
    state = load_state(cfg.pipeline, run_id)
    orch = Orchestrator(cfg, auto_yes=auto_yes)
    fn = getattr(orch, phase_fn_name)
    asyncio.run(fn(state))


@app.command()
def topic(
    run_id: Annotated[str, typer.Argument()],
    auto_yes: Annotated[bool, typer.Option("--yes", help="non-critical CP 自動套用")] = False,
) -> None:
    """Phase 1：題目守門員 → CP1。"""

    _orch_run("phase_topic", run_id, auto_yes)


@app.command()
def pico(
    run_id: Annotated[str, typer.Argument()],
    auto_yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Phase 2：PICO 建構員 → CP2。"""

    _orch_run("phase_pico", run_id, auto_yes)


@app.command()
def search(
    run_id: Annotated[str, typer.Argument()],
    cochrane_ris: Annotated[Optional[Path], typer.Option()] = None,
    cinahl_ris: Annotated[Optional[Path], typer.Option()] = None,
    airiti_ris: Annotated[Optional[Path], typer.Option()] = None,
    auto_yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Phase 3：搜尋策略師 → CP3 → DB 檢索 + 去重 + DOI 驗證 → CP4。"""

    cfg = _load_cfg()
    state = load_state(cfg.pipeline, run_id)
    orch = Orchestrator(cfg, auto_yes=auto_yes)

    imports: dict[SourceDB, Path] = {}
    if cochrane_ris:
        imports[SourceDB.COCHRANE] = cochrane_ris
    if cinahl_ris:
        imports[SourceDB.CINAHL] = cinahl_ris
    if airiti_ris:
        imports[SourceDB.AIRITI] = airiti_ris

    asyncio.run(orch.phase_search(state, manual_imports=imports or None))


@app.command()
def appraise(
    run_id: Annotated[str, typer.Argument()],
    auto_yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Phase 4：CASP 評讀員（並行）→ CP5。"""

    _orch_run("phase_appraise", run_id, auto_yes)


@app.command()
def synthesise(
    run_id: Annotated[str, typer.Argument()],
    auto_yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Phase 5：綜整整合員 → CP6。"""

    _orch_run("phase_synthesise", run_id, auto_yes)


@app.command()
def write(
    run_id: Annotated[str, typer.Argument()],
    auto_yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Phase 6：分節撰寫員（並行）→ CP7。"""

    _orch_run("phase_write", run_id, auto_yes)


@app.command()
def check(
    run_id: Annotated[str, typer.Argument()],
    auto_yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Phase 7：語氣守門員 + APA 7 格式員（並行）→ CP8。"""

    _orch_run("phase_check", run_id, auto_yes)


@app.command()
def render(
    run_id: Annotated[str, typer.Argument()],
    auto_yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Phase 8：Quarto render → DRAFT DOCX → CP9。"""

    _orch_run("phase_render", run_id, auto_yes)


@app.command("run")
def run_all(
    run_id: Annotated[str, typer.Argument()],
    auto_yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """End-to-end：從當前 phase 跑到 phase_render。"""

    cfg = _load_cfg()
    state = load_state(cfg.pipeline, run_id)
    orch = Orchestrator(cfg, auto_yes=auto_yes)

    async def _run() -> None:
        phase_map = [
            (PipelinePhase.INIT, orch.phase_topic),
            (PipelinePhase.TOPIC, orch.phase_pico),
            (PipelinePhase.PICO, orch.phase_search),
            (PipelinePhase.SEARCH, orch.phase_appraise),
            (PipelinePhase.APPRAISE, orch.phase_synthesise),
            (PipelinePhase.SYNTHESISE, orch.phase_write),
            (PipelinePhase.WRITE, orch.phase_check),
            (PipelinePhase.CHECK, orch.phase_render),
        ]
        current = state
        for expected_before, fn in phase_map:
            if list(PipelinePhase).index(current.current_phase) < list(PipelinePhase).index(expected_before):
                continue
            current = await fn(current)

    asyncio.run(_run())


@app.command()
def status(run_id: Annotated[str, typer.Argument()]) -> None:
    """顯示目前 phase 與 checkpoint 紀錄。"""

    cfg = _load_cfg()
    state = load_state(cfg.pipeline, run_id)
    console.print(
        f"[bold]Run:[/] {state.config.run_id}\n"
        f"[bold]Type:[/] {state.config.report_type.value}\n"
        f"[bold]Topic:[/] {state.config.user_topic_raw}\n"
        f"[bold]Phase:[/] {state.current_phase.value}\n"
        f"[bold]Updated:[/] {state.updated_at.isoformat(timespec='seconds')}\n"
    )
    table = Table(title="Checkpoint log")
    table.add_column("CP")
    table.add_column("Time")
    table.add_column("Choice")
    table.add_column("Rationale")
    for c in state.checkpoints:
        table.add_row(
            c.cp_id.value,
            c.timestamp.isoformat(timespec="seconds"),
            c.user_choice,
            c.rationale or "",
        )
    console.print(table)


if __name__ == "__main__":
    app()
