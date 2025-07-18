"""
Step 5 – tds_reconciliation.py
Combines TDS‑payable (Tally), calculated TDS, and Form 26Q data to produce a
two‑sheet reconciliation workbook plus a vendor‑level summary.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from tds_app.config.settings import \
    settings  # not yet used, but imported for future path tweaks

# ─── logger ─────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


# ─── Core routine ───────────────────────────────────────────────────────
def run_step5() -> None:
    # --- 1️⃣ Load the three source sheets ---------------------------------
    tally_df = pd.read_excel("tdspayable_tally.xlsx")
    expense_raw = pd.read_excel("processed_expense_data_with_tds.xlsx")
    expense_df = expense_raw[
        expense_raw["TDS Applicable"].astype(str).str.strip().str.upper() == "YES"
    ].copy()
    form26q_df = pd.read_excel("parsed_26Q.xlsx")

    # --- 2️⃣ Clean & standardise keys ------------------------------------
    def _clean(s):  # helper
        return s.astype(str).str.strip().str.upper()

    tally_df["Month_clean"] = _clean(tally_df["Month"])
    tally_df["Vendor_clean"] = _clean(tally_df["Vendor"])

    expense_df["Month_clean"] = _clean(expense_df["Month"])
    expense_df["Vendor_clean"] = _clean(expense_df["Vendor Associated"])
    expense_df["PAN_clean"] = _clean(expense_df["PAN"])

    form26q_df["Month_clean"] = _clean(form26q_df["Month"])
    form26q_df["Vendor_clean"] = _clean(form26q_df["Vendor"])
    form26q_df["PAN_clean"] = _clean(form26q_df["PAN"])

    # --- 3️⃣ Aggregate Tally TDS Payable ---------------------------------
    tally_agg = (
        tally_df.groupby(["Month_clean", "Vendor_clean"])["TDS Amount"]
        .sum()
        .reset_index()
        .rename(columns={"TDS Amount": "TDS as per Tally"})
    )

    # --- 4️⃣ Aggregate Calculated TDS (Expense Data) ---------------------
    calc_df = (
        expense_df.groupby(["Month_clean", "Vendor_clean", "PAN_clean", "TDS Section"])
        .agg({"Amount": "sum", "TDS Amount": "sum"})
        .reset_index()
        .rename(
            columns={
                "Amount": "Amount Paid as per Tally",
                "TDS Amount": "TDS as per Calculation",
                "TDS Section": "Section as per Tally",
            }
        )
    )

    # --- 5️⃣ Aggregate Form 26Q ------------------------------------------
    q26_df = (
        form26q_df.groupby(["Month_clean", "Vendor_clean", "PAN_clean", "Section"])
        .agg({"Amount Paid": "sum", "TDS Deducted": "sum"})
        .reset_index()
        .rename(
            columns={
                "Amount Paid": "Amount Paid as per 26Q",
                "TDS Deducted": "TDS as per 26Q",
                "Section": "Section as per 26Q",
            }
        )
    )

    # --- 6A Merge Tally & Calc -------------------------------------------
    merged_calc_tally = pd.merge(
        calc_df, tally_agg, on=["Month_clean", "Vendor_clean"], how="outer"
    )

    # --- 6B Merge with 26Q ------------------------------------------------
    merged_calc_tally["PAN_clean"] = merged_calc_tally["PAN_clean"].fillna("NA")
    q26_df["PAN_clean"] = q26_df["PAN_clean"].fillna("NA")

    final_df = pd.merge(
        merged_calc_tally,
        q26_df,
        left_on=["Month_clean", "PAN_clean", "Section as per Tally"],
        right_on=["Month_clean", "PAN_clean", "Section as per 26Q"],
        how="outer",
    )

    # --- 7️⃣ Create final columns ----------------------------------------
    final_df["Month"] = final_df["Month_clean"]

    # Prefer vendor from calc/tally side, fallback to 26Q side
    final_df["Vendor Name"] = final_df["Vendor_clean_x"].combine_first(
        final_df["Vendor_clean_y"]
    )
    final_df["PAN"] = final_df["PAN_clean"]

    # --- 8️⃣ Ensure numeric types ----------------------------------------
    for col in [
        "Amount Paid as per Tally",
        "Amount Paid as per 26Q",
        "TDS as per Tally",
        "TDS as per 26Q",
        "TDS as per Calculation",
    ]:
        final_df[col] = pd.to_numeric(final_df[col], errors="coerce")

    # --- 9️⃣ Difference columns & section check --------------------------
    final_df["Difference TDS Tally vs 26Q"] = (
        final_df["TDS as per Tally"] - final_df["TDS as per 26Q"]
    ).round(2)
    final_df["Difference TDS Calculation vs 26Q"] = (
        final_df["TDS as per Calculation"] - final_df["TDS as per 26Q"]
    ).round(2)
    final_df["Difference Amount Tally vs 26Q"] = (
        final_df["Amount Paid as per Tally"] - final_df["Amount Paid as per 26Q"]
    ).round(2)

    final_df["Difference Section Tally vs 26Q"] = (
        final_df["Section as per Tally"] != final_df["Section as per 26Q"]
    )

    # --- 🔟 Column order & sorting ---------------------------------------
    cols_order = [
        "Month",
        "Vendor Name",
        "PAN",
        "Section as per Tally",
        "Section as per 26Q",
        "Amount Paid as per Tally",
        "Amount Paid as per 26Q",
        "TDS as per Calculation",
        "TDS as per Tally",
        "TDS as per 26Q",
        "Difference TDS Tally vs 26Q",
        "Difference TDS Calculation vs 26Q",
        "Difference Amount Tally vs 26Q",
        "Difference Section Tally vs 26Q",
    ]
    final_df = final_df[cols_order].sort_values(by=["Month", "Vendor Name", "PAN"])

    # --- ✅ Export workbook ----------------------------------------------
    output_path = Path("tds_reconciliation_report.xlsx")
    final_df.to_excel(output_path, index=False)

    # Vendor‑PAN summary sheet
    vendor_summary = (
        final_df.groupby(["Vendor Name", "PAN"], dropna=False)
        .agg(
            {
                "Amount Paid as per Tally": "sum",
                "Amount Paid as per 26Q": "sum",
                "TDS as per Calculation": "sum",
                "TDS as per Tally": "sum",
                "TDS as per 26Q": "sum",
            }
        )
        .reset_index()
    )
    vendor_summary["Difference TDS Tally vs 26Q"] = (
        vendor_summary["TDS as per Tally"] - vendor_summary["TDS as per 26Q"]
    ).round(2)
    vendor_summary["Difference TDS Calculation vs 26Q"] = (
        vendor_summary["TDS as per Calculation"] - vendor_summary["TDS as per 26Q"]
    ).round(2)
    vendor_summary["Difference Amount Tally vs 26Q"] = (
        vendor_summary["Amount Paid as per Tally"]
        - vendor_summary["Amount Paid as per 26Q"]
    ).round(2)

    with pd.ExcelWriter(output_path, engine="openpyxl", mode="w") as writer:
        final_df.to_excel(writer, sheet_name="Monthwise Reconciliation", index=False)
        vendor_summary.to_excel(writer, sheet_name="Vendor-PAN Summary", index=False)

    logger.info("Reconciliation completed → %s", output_path)

    # Totals validation logs
    logger.info("Total TDS as per Tally       : %s", final_df["TDS as per Tally"].sum())
    logger.info(
        "Total TDS as per Calculation : %s",
        final_df["TDS as per Calculation"].sum(),
    )
    logger.info("Total TDS as per Form 26Q    : %s", final_df["TDS as per 26Q"].sum())


# ─── Public wrapper for Typer CLI ───────────────────────────────────────
def run_step5_cli() -> None:
    """Runs final reconciliation (Step 5)."""
    run_step5()


if __name__ == "__main__":
    run_step5()
