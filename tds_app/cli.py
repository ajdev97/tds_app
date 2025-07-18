"""
TDS App – command‑line interface.
Run `tds-app --help` once installed.
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich import print  # noqa: T201  (rich.print is fine for help colours)

from tds_app.config.settings import settings
from tds_app.logging_config import setup_logging

# ---------------------------------------------------------------------- #
#   Logging setup – root logger uses Rich handler defined centrally
# ---------------------------------------------------------------------- #
setup_logging("DEBUG" if settings.verbose else "INFO")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------- #
#   Import step wrappers
# ---------------------------------------------------------------------- #
from tds_app.steps.step1_tds_section_mapper import run_step1
from tds_app.steps.step2_prepare_expense_data import run_step2_cli
from tds_app.steps.step3_tdspayable_reco import run_step3_cli
from tds_app.steps.step4_parse_26q import run_step4_cli
from tds_app.steps.step5_tds_reconciliation import run_step5_cli

__version__ = "0.1.0"

# ── root Typer application ──────────────────────────────────────────────
app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help=f"TDS automation toolkit (v {__version__})",
)


@app.callback()
def _root() -> None:
    """TDS‑App command group (root callback needed for sub‑commands)."""


# ── Sanity‑check command ────────────────────────────────────────────────
@app.command()
def hello() -> None:
    """Print a friendly greeting (sanity check)."""
    logger.info(":sparkles:  Hello from [bold cyan]TDS App[/]!")


# ── Step 1: section‑map ─────────────────────────────────────────────────
@app.command("section-map")
def section_map(
    daybook: Path = typer.Argument(..., exists=True, help="Path to Daybook.xlsx"),
) -> None:
    """Run Step 1 – map ledgers to TDS sections."""
    logger.info("▶ Step 1 – mapping ledgers…")
    run_step1(str(daybook))
    logger.info("✓ Step 1 done")


# ── Step 2: prepare‑expense ─────────────────────────────────────────────
@app.command("prepare-expense")
def prepare_expense(
    daybook: Path = typer.Argument(..., exists=True, help="Daybook.xlsx file"),
    ledger: Path = typer.Argument(..., exists=True, help="Ledger.xlsx file"),
    turnover_gt_10cr: bool = typer.Option(
        False,
        help="Set if previous‑year turnover exceeded ₹10 crore "
        "(affects 194Q applicability).",
    ),
) -> None:
    """Run Step 2 – prepare expense data."""
    logger.info("▶ Step 2 – preparing expense data…")
    run_step2_cli(str(daybook), str(ledger), turnover_gt_10cr)
    logger.info("✓ Step 2 done")


# ── Step 3: tds‑payable ────────────────────────────────────────────────
@app.command("tds-payable")
def tds_payable() -> None:
    """Run Step 3 – TDS payable reconciliation."""
    logger.info("▶ Step 3 – reconciling TDS payable…")
    run_step3_cli()
    logger.info("✓ Step 3 done")


# ── Step 4: parse‑26q ──────────────────────────────────────────────────
@app.command("parse-26q")
def parse_26q(
    form26q: Path = typer.Argument(..., exists=True, help="26Q Word file"),
) -> None:
    """Run Step 4 – parse 26Q document."""
    logger.info("▶ Step 4 – parsing 26Q…")
    run_step4_cli(str(form26q))
    logger.info("✓ Step 4 done")


# ── Step 5: final‑reco ─────────────────────────────────────────────────
@app.command("final-reco")
def final_reco() -> None:
    """Run Step 5 – final reconciliation."""
    logger.info("▶ Step 5 – final reconciliation…")
    run_step5_cli()
    logger.info("🎉  Reconciliation complete")


# ── Pipeline: run‑all ──────────────────────────────────────────────────
@app.command("run-all")
def run_all(
    daybook: Path = typer.Option("Daybook.xlsx", exists=True, help="Daybook file"),
    ledger: Path = typer.Option("Ledger.xlsx", exists=True, help="Ledger file"),
    form26q: Path = typer.Option("26Q.docx", exists=True, help="26Q Word file"),
    turnover_gt_10cr: bool = typer.Option(
        False,
        help="Set if previous‑year turnover exceeded ₹10 crore "
        "(affects 194Q applicability).",
    ),
) -> None:
    """Run the full 5‑step pipeline in sequence."""
    section_map(daybook)
    prepare_expense(daybook, ledger, turnover_gt_10cr=turnover_gt_10cr)
    tds_payable()
    parse_26q(form26q)
    final_reco()
    logger.info("🏁  Full pipeline finished")


# ── Entry‑point for `python -m tds_app.cli` -----------------------------
def main() -> None:  # noqa: D401
    """CLI entry‑point."""
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
