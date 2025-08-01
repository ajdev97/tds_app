"""
Step 3 – TDS‑payable reconciliation.
Builds tdspayable_tally.xlsx, identifies unconsidered vouchers, and
exports a two‑sheet reconciliation workbook.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import xlsxwriter  # needed for conditional formatting & autofit

from tds_app.config.settings import settings

# ─── logger ─────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ─── Constants (wrapper can override DAYBOOK_FILE if needed) ────────────
DAYBOOK_FILE = settings.daybook_file
PROCESSED_FILE = "processed_expense_data_with_tds.xlsx"


# ─── Utility: Excel column autofit ──────────────────────────────────────
def _autofit_columns(df: pd.DataFrame, worksheet) -> None:
    for idx, col in enumerate(df.columns):
        max_len = max(df[col].astype(str).map(len).max(), len(col))
        worksheet.set_column(idx, idx, max_len + 2)


# ─── Core logic ─────────────────────────────────────────────────────────
def run_step3() -> None:
    logger.info("▶ Step 3 – reading input files…")
    
    # Check if required files exist
    if not Path(DAYBOOK_FILE).exists():
        raise FileNotFoundError(f"Daybook file not found: {DAYBOOK_FILE}")
    if not Path(PROCESSED_FILE).exists():
        raise FileNotFoundError(f"Processed expense file not found: {PROCESSED_FILE}")
    
    daybook_df = pd.read_excel(DAYBOOK_FILE, sheet_name="Sheet1")
    processed_df = pd.read_excel(PROCESSED_FILE)

    # 1️⃣ Preprocess group
    daybook_df["$Led_Group_Clean"] = daybook_df["$Led_Group"].str.strip().str.lower()

    # 2️⃣ Filter valid TDS ledgers (exclude Salary & 192)
    tds_ledger_mask = (
        (daybook_df["$Led_Group_Clean"] == "duties & taxes")
        & (daybook_df["$LedgerName"].str.upper().str.contains("TDS",    na=False))
        & (~daybook_df["$LedgerName"].str.upper().str.contains("SALARY", na=False))
        & (~daybook_df["$LedgerName"].str.contains(r"\b192\b", case=False, regex=True, na=False))
    )

    tds_ledgers_used = sorted(daybook_df.loc[tds_ledger_mask, "$LedgerName"].unique())
    logger.info("TDS Ledgers used (filtered): %s", tds_ledgers_used)

    # 3️⃣ vouchers with TDS ledgers
    keys_with_tds = daybook_df.loc[tds_ledger_mask, "$Key"].unique()
    tds_txn_df = daybook_df[daybook_df["$Key"].isin(keys_with_tds)].copy()

    # 4️⃣ flags & vendor map
    expense_groups = {
        "direct expenses",
        "indirect expenses",
        "purchase accounts",
        "fixed assets",
    }

    expense_key_flag = (
        tds_txn_df.groupby("$Key")["$Led_Group_Clean"]
        .apply(lambda g: any(grp in expense_groups for grp in g))
        .to_dict()
    )

    vendor_map = (
        tds_txn_df[
            tds_txn_df["$Led_Group_Clean"].isin(["sundry creditors", "unsecured loans"])
        ]
        .groupby("$Key")["$LedgerName"]
        .first()
        .to_dict()
    )

    # 5️⃣ sign helper
    def apply_sign(amount, tds_sign_reference):
        amt = round(abs(amount), 2)
        return -amt if tds_sign_reference < 0 else amt

    # 6️⃣ build records
    records: list[dict] = []
    not_considered: list[dict] = []

    for key in keys_with_tds:
        txn_rows = tds_txn_df[tds_txn_df["$Key"] == key]
        has_exp = expense_key_flag.get(key, False)

        tds_rows = txn_rows[
            (txn_rows["$LedgerName"].isin(tds_ledgers_used))
            & (txn_rows["$Led_Group_Clean"] == "duties & taxes")
        ]
        tds_sign_reference = tds_rows["$Amount"].iloc[0] if not tds_rows.empty else 0

        # — Case A: Auto —
        if has_exp:
            amt_rows = tds_rows
            vendor_name = vendor_map.get(key)

            if vendor_name:
                for _, r in amt_rows.iterrows():
                    records.append(
                        {
                            "Month": pd.to_datetime(r["$Date"]).strftime("%b-%y"),
                            "Vendor": vendor_name,
                            "TDS Ledger": r["$LedgerName"],
                            "TDS Amount": apply_sign(r["$Amount"], tds_sign_reference),
                            "Entry Type": "Auto",
                        }
                    )
            else:
                voucher_type = (
                    txn_rows["$VoucherTypeName"].iloc[0]
                    if "$VoucherTypeName" in txn_rows.columns
                    else "Unknown"
                )
                not_considered.append(
                    {"Voucher Key": key, "Voucher Type": voucher_type}
                )

        # — Case B: Fallback —
        else:
            creditor_rows = txn_rows[
                txn_rows["$Led_Group_Clean"].isin(
                    ["sundry creditors", "unsecured loans"]
                )
            ]

            if len(creditor_rows) > 1:
                for _, r in creditor_rows.iterrows():
                    records.append(
                        {
                            "Month": pd.to_datetime(r["$Date"]).strftime("%b-%y"),
                            "Vendor": r["$LedgerName"],
                            "TDS Ledger": r["$LedgerName"],
                            "TDS Amount": apply_sign(r["$Amount"], tds_sign_reference),
                            "Entry Type": "Fallback",
                        }
                    )
            elif len(creditor_rows) == 1:
                r = creditor_rows.iloc[0]
                records.append(
                    {
                        "Month": pd.to_datetime(r["$Date"]).strftime("%b-%y"),
                        "Vendor": r["$LedgerName"],
                        "TDS Ledger": r["$LedgerName"],
                        "TDS Amount": apply_sign(r["$Amount"], tds_sign_reference),
                        "Entry Type": "Fallback",
                    }
                )
            else:
                voucher_type = (
                    txn_rows["$VoucherTypeName"].iloc[0]
                    if "$VoucherTypeName" in txn_rows.columns
                    else "Unknown"
                )
                not_considered.append(
                    {"Voucher Key": key, "Voucher Type": voucher_type}
                )

    # 7️⃣ export tally
    tds_payable_tally = pd.DataFrame(records)
    tally_path = Path("tdspayable_tally.xlsx")
    tds_payable_tally.to_excel(tally_path, index=False)
    logger.info("Exported: %s", tally_path)

    # 8️⃣ export not‑considered
    if not_considered:
        not_cons_path = Path("tdspayabletally_notconsidered.xlsx")
        pd.DataFrame(not_considered).to_excel(not_cons_path, index=False)
        logger.info("Exported: %s (%d entries)", not_cons_path, len(not_considered))
    else:
        logger.info("All considered vouchers had a Sundry Creditor ledger.")

    # 9️⃣ reconciliation dataframes
    tally_grouped = (
        tds_payable_tally.groupby(["Month", "Vendor"])["TDS Amount"]
        .sum()
        .reset_index()
        .rename(columns={"TDS Amount": "TDS as per Tally"})
    )

    calc_df = processed_df[processed_df["TDS Applicable"] == "Yes"][
        ["Month", "Vendor Associated", "TDS Amount", "TDS Section"]
    ].copy()
    calc_df = calc_df.rename(columns={"Vendor Associated": "Vendor"})

    calc_grouped = (
        calc_df.groupby(["Month", "Vendor", "TDS Section"])["TDS Amount"]
        .sum()
        .reset_index()
        .rename(columns={"TDS Amount": "TDS as per Calculation"})
    )

    tds_reco = pd.merge(
        calc_grouped, tally_grouped, on=["Month", "Vendor"], how="outer"
    ).fillna(0)

    tds_reco["TDS as per Calculation"] = tds_reco["TDS as per Calculation"].round(2)
    tds_reco["TDS as per Tally"] = tds_reco["TDS as per Tally"].round(2)
    tds_reco["Difference"] = (
        tds_reco["TDS as per Calculation"] - tds_reco["TDS as per Tally"]
    ).round(2)

    # 🔟 Excel export
    logger.info("Writing reconciliation workbook…")
    reco_path = Path("tdspayable_reco.xlsx")

    with pd.ExcelWriter(reco_path, engine="xlsxwriter") as writer:
        # sheet 1
        tds_reco.to_excel(writer, index=False, sheet_name="Month-wise Reco")

        # sheet 2
        tds_reco["TDS Section"] = (
            tds_reco["TDS Section"].replace("0", pd.NA).replace("", pd.NA)
        )
        section_map = (
            tds_reco.dropna(subset=["TDS Section"])
            .groupby("Vendor")["TDS Section"]
            .first()
            .to_dict()
        )
        tds_reco["TDS Section"] = tds_reco["Vendor"].map(section_map).fillna("Unknown")
        summary = (
            tds_reco.groupby(["Vendor", "TDS Section"])[
                ["TDS as per Calculation", "TDS as per Tally"]
            ]
            .sum()
            .reset_index()
        )
        summary["Difference"] = (
            summary["TDS as per Calculation"] - summary["TDS as per Tally"]
        ).round(2)
        summary.to_excel(writer, index=False, sheet_name="Vendor-wise Summary")

        workbook = writer.book
        red_fmt = workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})

        ws1 = writer.sheets["Month-wise Reco"]
        rows1 = len(tds_reco)
        ws1.conditional_format(
            f"E2:E{rows1 + 1}",
            {"type": "cell", "criteria": "greater than", "value": 1, "format": red_fmt},
        )
        ws1.conditional_format(
            f"E2:E{rows1 + 1}",
            {"type": "cell", "criteria": "less than", "value": -1, "format": red_fmt},
        )
        _autofit_columns(tds_reco, ws1)

        ws2 = writer.sheets["Vendor-wise Summary"]
        rows2 = len(summary)
        ws2.conditional_format(
            f"D2:D{rows2 + 1}",
            {"type": "cell", "criteria": "greater than", "value": 1, "format": red_fmt},
        )
        ws2.conditional_format(
            f"D2:D{rows2 + 1}",
            {"type": "cell", "criteria": "less than", "value": -1, "format": red_fmt},
        )
        _autofit_columns(summary, ws2)

    logger.info("Exported: %s with two sheets and formatting.", reco_path)

    # summary totals
    logger.info(
        "Summary Totals:\n%s",
        tds_reco[["TDS as per Calculation", "TDS as per Tally", "Difference"]].sum(),
    )


# ─── Public wrapper for Typer CLI ───────────────────────────────────────
def run_step3_cli() -> None:
    """Execute Step 3 via CLI wrapper."""
    run_step3()


if __name__ == "__main__":
    run_step3()
