"""Mercury CLI."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Optional

# Force UTF-8 stdio on Windows consoles whose default codepage is gbk/cp936.
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from mercury.config import PLOTS_DIR, PROJECT_ROOT, RESULTS_DIR, SKILL_LIBRARY_DIR
from mercury.eval.metrics import compare, compute
from mercury.eval.plots import render_all
from mercury.eval.runner import (
    BenchResult,
    TaskResult,
    load_bench,
    metrics_path,
    run_bench,
    run_one_task,
    save_bench,
)
from mercury.eval.tasks import Task, all_tasks, get_task
from mercury.skills.loader import manifest_to_dicts, scan_manifest


# Eagerly load .env so DASHSCOPE_API_KEY is visible to subprocesses too.
load_dotenv(PROJECT_ROOT / ".env", override=False)


app = typer.Typer(
    help="Mercury — self-evolving skill synthesis agent.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


_VALID_MODES = ("baseline", "evolve", "evolved")


def _parse_task_filter(spec: Optional[str]) -> Optional[list[str]]:
    """`--tasks csv-001,csv-002` → ['csv-001', 'csv-002']; None → None."""
    if not spec:
        return None
    return [tid.strip() for tid in spec.split(",") if tid.strip()]


def _print_run_summary(result: TaskResult, *, mode: str) -> None:
    table = Table(title="Run summary", show_header=True, header_style="bold")
    table.add_column("metric")
    table.add_column("value")
    table.add_row("passed", "[green]PASS[/green]" if result.success else "[red]FAIL[/red]")
    table.add_row("turns (LLM steps)", str(result.turns))
    table.add_row("tokens", str(result.tokens))
    table.add_row("trace file", result.trace_path)
    if mode == "evolve" and not result.synthesized_skill_path:
        table.add_row("synthesis", "[dim](evaluator declined or gate skipped)[/dim]")
    if result.synthesized_skill_path:
        table.add_row("SKILL.md written", result.synthesized_skill_path)
    if result.verifier_verdict:
        colour = "green" if result.verifier_verdict == "verified" else "red"
        table.add_row(
            "verifier verdict",
            f"[{colour}]{result.verifier_verdict}[/{colour}]",
        )
        if result.rejection_reason:
            table.add_row("rejection reason", result.rejection_reason)
    console.print(table)
    if not result.success:
        reason = result.last_reason or "(submit was never called or never passed)"
        console.print(f"[yellow]reason:[/yellow] {reason}")


# ---------------------------------------------------------------- run


@app.command("run")
def run(
    task: str = typer.Option(..., "--task", "-t", help="Task ID, e.g. csv-001"),
    mode: str = typer.Option(
        "baseline",
        "--mode",
        "-m",
        help="Run mode: baseline | evolve | evolved",
    ),
    run_idx: int = typer.Option(0, "--run-idx", help="Run index for trace filename"),
):
    """Run a single task end-to-end through the executor loop."""
    if mode not in _VALID_MODES:
        console.print(f"[red]invalid --mode: {mode}[/red]")
        raise typer.Exit(2)

    t = get_task(task)
    console.print(f"[cyan bold]task:[/cyan bold] {t.id}   [cyan]mode:[/cyan] {mode}")
    if mode == "evolved":
        n = len(manifest_to_dicts(scan_manifest(status="verified")))
        if n:
            console.print(f"[dim]manifest:[/dim] {n} verified skill(s) loaded")

    try:
        result = run_one_task(t, mode=mode, run_idx=run_idx)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Run failed:[/red] {e}")
        raise typer.Exit(1) from e

    console.print(f"[dim]workspace:[/dim] {result.workspace}")
    _print_run_summary(result, mode=mode)
    raise typer.Exit(0 if result.success else 1)


# ---------------------------------------------------------------- list-tasks


@app.command("list-tasks")
def list_tasks():
    """List all registered tasks."""
    table = Table(title="Tasks", show_header=True, header_style="bold")
    table.add_column("id")
    table.add_column("group")
    table.add_column("description")
    for t in all_tasks():
        table.add_row(t.id, t.group, t.description[:90])
    console.print(table)


# ---------------------------------------------------------------- bench


def _run_bench_impl(mode: str, task_ids: Optional[list[str]]) -> None:
    """Shared body of `mercury bench` and `mercury evolve` (full-suite path)."""
    if mode not in _VALID_MODES:
        console.print(f"[red]invalid --mode: {mode}[/red]")
        raise typer.Exit(2)

    selected = task_ids or [t.id for t in all_tasks()]
    console.print(
        f"[cyan bold]bench[/cyan bold] mode=[cyan]{mode}[/cyan] · "
        f"{len(selected)} task(s): {', '.join(selected)}"
    )

    def _progress(idx: int, total: int, t: Task, result: Optional[TaskResult]) -> None:
        if result is None:
            console.print(f"[dim]({idx + 1}/{total})[/dim] {t.id}…")
        else:
            tag = "[green]PASS[/green]" if result.success else "[red]FAIL[/red]"
            extra: list[str] = []
            if result.synthesized_skill_path:
                extra.append(f"skill={Path(result.synthesized_skill_path).parent.name}")
            if result.verifier_verdict:
                extra.append(f"verdict={result.verifier_verdict}")
            tail = (" " + " ".join(extra)) if extra else ""
            console.print(
                f"  → {tag}  turns={result.turns}  tokens={result.tokens}{tail}"
            )

    bench_result = run_bench(mode, task_ids=task_ids, progress_cb=_progress)
    saved = save_bench(bench_result)
    metrics = compute(bench_result)

    table = Table(title=f"bench summary  [{mode}]", show_header=True, header_style="bold")
    table.add_column("metric")
    table.add_column("value")
    table.add_row("n", str(metrics.n))
    table.add_row("Pass@1", f"{metrics.pass_at_1:.2%}")
    table.add_row("avg tokens", f"{metrics.avg_tokens:.0f}")
    table.add_row("avg turns", f"{metrics.avg_turns:.2f}")
    for group, gs in metrics.by_group.items():
        table.add_row(
            f"  · {group} (n={gs.n})",
            f"Pass@1={gs.pass_at_1:.2%}  tokens={gs.avg_tokens:.0f}  turns={gs.avg_turns:.2f}",
        )
    table.add_row("metrics file", str(saved))
    console.print(table)


@app.command()
def bench(
    mode: str = typer.Option("baseline", "--mode", "-m", help="baseline | evolve | evolved"),
    tasks: Optional[str] = typer.Option(
        None,
        "--tasks",
        help="Comma-separated task IDs (e.g. 'csv-001,csv-002'). Default: all tasks.",
    ),
):
    """Run a benchmark across all (or selected) tasks; persist `metrics_<mode>.json`."""
    _run_bench_impl(mode, _parse_task_filter(tasks))


# ---------------------------------------------------------------- evolve


@app.command()
def evolve(
    task: Optional[str] = typer.Option(
        None, "--task", "-t", help="Evolve from a single task; omit to run the full task suite."
    ),
    tasks: Optional[str] = typer.Option(
        None,
        "--tasks",
        help="Comma-separated task IDs to evolve. Mutually exclusive with --task.",
    ),
    run_idx: int = typer.Option(0, "--run-idx", help="Run index for trace filenames."),
):
    """Run the evolve loop: executor → evaluator → (synthesizer → verifier | END).

    Successful synthesises trigger inline verification; verified skills land in
    `skills/library/<name>/` (`status: verified`), rejected ones in `_rejected/`.
    """
    if task:
        if tasks:
            console.print("[red]--task and --tasks are mutually exclusive[/red]")
            raise typer.Exit(2)
        # Single-task path: reuse the existing run summary UX.
        t = get_task(task)
        console.print(f"[cyan bold]task:[/cyan bold] {t.id}   [cyan]mode:[/cyan] evolve")
        try:
            result = run_one_task(t, mode="evolve", run_idx=run_idx)
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]Run failed:[/red] {e}")
            raise typer.Exit(1) from e
        console.print(f"[dim]workspace:[/dim] {result.workspace}")
        _print_run_summary(result, mode="evolve")
        raise typer.Exit(0 if result.success else 1)
    _run_bench_impl("evolve", _parse_task_filter(tasks))


# ---------------------------------------------------------------- report


@app.command()
def report():
    """Generate plots + comparison table from the saved bench metrics."""
    bp = metrics_path("baseline")
    ep = metrics_path("evolved")
    if not bp.exists():
        console.print(
            f"[red]missing[/red] {bp.name}; run "
            f"[cyan]mercury bench --mode baseline[/cyan] first"
        )
        raise typer.Exit(2)
    if not ep.exists():
        console.print(
            f"[red]missing[/red] {ep.name}; run "
            f"[cyan]mercury bench --mode evolved[/cyan] first"
        )
        raise typer.Exit(2)

    baseline = load_bench(bp)
    evolved = load_bench(ep)
    cmp_ = compare(baseline, evolved)

    table = Table(title="baseline → evolved", show_header=True, header_style="bold")
    table.add_column("metric")
    table.add_column("baseline")
    table.add_column("evolved")
    table.add_column("Δ / ratio")
    table.add_row(
        "n",
        str(cmp_.baseline.n),
        str(cmp_.evolved.n),
        "-",
    )
    table.add_row(
        "Pass@1",
        f"{cmp_.baseline.pass_at_1:.2%}",
        f"{cmp_.evolved.pass_at_1:.2%}",
        f"Δ={cmp_.pass_delta:+.2%}  g={cmp_.normalized_gain:+.2f}",
    )
    table.add_row(
        "avg tokens",
        f"{cmp_.baseline.avg_tokens:.0f}",
        f"{cmp_.evolved.avg_tokens:.0f}",
        f"×{cmp_.tokens_ratio:.3f}" if cmp_.tokens_ratio is not None else "—",
    )
    table.add_row(
        "avg turns",
        f"{cmp_.baseline.avg_turns:.2f}",
        f"{cmp_.evolved.avg_turns:.2f}",
        f"×{cmp_.turns_ratio:.3f}" if cmp_.turns_ratio is not None else "—",
    )
    console.print(table)

    plot_paths = render_all(baseline, evolved, out_dir=PLOTS_DIR)
    console.print(f"[green]✓[/green] wrote {len(plot_paths)} plots:")
    for p in plot_paths:
        console.print(f"  · {p}")


# ---------------------------------------------------------------- reset


@app.command()
def reset():
    """Wipe the skill library (keeps .gitkeep). Use before clean baseline / evolve runs."""
    if not SKILL_LIBRARY_DIR.exists():
        console.print(f"[dim]library does not exist:[/dim] {SKILL_LIBRARY_DIR}")
        return
    removed = 0
    for child in SKILL_LIBRARY_DIR.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed += 1
    console.print(
        f"[green]reset[/green]: removed {removed} entries from {SKILL_LIBRARY_DIR}"
    )
    # Also clear the SqliteSaver state.db so checkpoints from a previous run
    # don't bleed across.
    db = RESULTS_DIR / "state.db"
    if db.exists():
        db.unlink()
        console.print(f"[green]reset[/green]: removed {db}")


if __name__ == "__main__":
    app()
