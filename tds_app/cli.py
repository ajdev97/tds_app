"""
TDS App – command‑line interface.
Run `tds-app --help` once installed.
"""

from __future__ import annotations

import logging  # ← add this
from pathlib import Path

import typer
from rich import print

from tds_app.config.settings import settings
from tds_app.logging_config import setup_logging

setup_logging("DEBUG" if settings.verbose else "INFO")

from tds_app.steps.step2_prepare_expense_data import run_step2_cli
from tds_app.steps.step3_tdspayable_reco import run_step3_cli
from tds_app.steps.step4_parse_26q import run_step4_cli
from tds_app.steps.step5_tds_reconciliation import run_step5_cli

__version__ = "0.1.0"

# ── root Typer application ────────────────────────────────────────────────
app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,  # show help if user types nothing
    help=f"TDS automation toolkit (v {__version__})",
)


# ── ROOT CALLBACK (required for sub‑commands!) ────────────────────────────
@app.callback()
def main_callback() -> None:  # noqa: D401
    """TDS‑App command group."""


# ── example sub‑command ───────────────────────────────────────────────────
logger = logging.getLogger(__name__)


@app.command()
def hello() -> None:
    """Print a friendly greeting (sanity check)."""
    logger.info(":sparkles:  Hello from [bold cyan]TDS App[/]!")


# ── Step 1: section‑map ─────────────────────────────────────────────────
from pathlib import Path

from tds_app.steps.step1_tds_section_mapper import run_step1


@app.command("section-map")
def section_map(
    daybook: Path = typer.Argument(..., exists=True, help="Path to Daybook.xlsx")
) -> None:
    """Run Step 1 – map ledgers to TDS sections."""
    print("[bold cyan]▶ Step 1 – mapping ledgers…[/]")
    run_step1(str(daybook))
    print("[green]✓ done[/]")


# ── Step 2: prepare‑expense ─────────────────────────────────────────────
@app.command("prepare-expense")
def prepare_expense(
    daybook: Path = typer.Argument(..., exists=True, help="Daybook.xlsx file"),
    ledger: Path = typer.Argument(..., exists=True, help="Ledger.xlsx file"),
) -> None:
    """Run Step 2 – prepare expense data."""
    print("[bold cyan]▶ Step 2 – preparing expense data…[/]")
    run_step2_cli(str(daybook), str(ledger))
    print("[green]✓ done[/]")


# ── Step 3: tdspayable‑reco ───────────────────────────────────────────
@app.command("tds-payable")
def tds_payable() -> None:
    """Run Step 3 – TDS payable reconciliation."""
    print("[bold cyan]▶ Step 3 – reconciling TDS payable…[/]")
    run_step3_cli()
    print("[green]✓ done[/]")


# ── Step 4: parse‑26q ────────────────────────────────────────────────
@app.command("parse-26q")
def parse_26q(
    form26q: Path = typer.Argument(..., exists=True, help="26Q Word file")
) -> None:
    """Run Step 4 – parse 26Q document."""
    print("[bold cyan]▶ Step 4 – parsing 26Q…[/]")
    run_step4_cli(str(form26q))
    print("[green]✓ done[/]")


# ── Step 5: final‑reco ───────────────────────────────────────────────
@app.command("final-reco")
def final_reco() -> None:
    """Run Step 5 – final reconciliation."""
    print("[bold cyan]▶ Step 5 – final reconciliation…[/]")
    run_step5_cli()
    print("[bold green]🎉  Reconciliation complete[/]")


# ── Pipeline: run‑all ───────────────────────────────────────────────────
@app.command("run-all")
def run_all(
    daybook: Path = typer.Option("Daybook.xlsx", exists=True),
    ledger: Path = typer.Option("Ledger.xlsx", exists=True),
    form26q: Path = typer.Option("26Q.docx", exists=True),
) -> None:
    """Run Steps 1–5 in order."""
    section_map(daybook)
    prepare_expense(daybook, ledger)
    tds_payable()
    parse_26q(form26q)
    final_reco()
    print("[bold green]🏁  Full pipeline finished[/]")


# ── allow `python -m tds_app.cli` and console script entry‑point ──────────
def main() -> None:  # noqa: D401
    """CLI entry‑point."""
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
