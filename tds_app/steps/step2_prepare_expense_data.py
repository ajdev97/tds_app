"""
Step 2 – prepare_expense_data.py
Enriches Daybook entries with PANs, TDS sections, applicability, and rates.

Dependencies (already in pyproject):
    pandas, numpy, openpyxl, XlsxWriter
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from tds_app.config.settings import settings

# ─── logger ─────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ─── Config (defaults – CLI wrapper can override) ───────────────────────
DAYBOOK_FILE = "Daybook.xlsx"
LEDGER_FILE = "Ledger.xlsx"
TDS_MAPPING_FILE = "ledger_tds_sections.csv"
TDS_RATES_FILE = "tds_rates.csv"
HARDCODED_VENDOR_FILE = "Hardcoded Vendors.csv"
OUTPUT_FILE = "processed_expense_data_with_tds.xlsx"
DISCREPANCY_FILE = "Discrepancies.xlsx"
DAYBOOK_SHEET = "A__DayBook"
LEDGER_SHEET = "Ledger"
GROUP_FILTER = [
    "Direct Expenses",
    "Indirect Expenses",
    "Purchase Accounts",
    "Fixed Assets",
]


def _normalize(name: str) -> str:  # CHG
    """Lower‑case, strip punctuation, collapse spaces (internal key)."""
    s = str(name).strip().lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return " ".join(s.split())


# ─── Main routine ───────────────────────────────────────────────────────
def run_step2(turnover_gt_10cr: bool = False) -> None:
    # --- Load Data ------------------------------------------------------
    logger.info("Reading Daybook & Ledger …")
    daybook_df = pd.read_excel(DAYBOOK_FILE, sheet_name=DAYBOOK_SHEET)
    ledger_df = pd.read_excel(LEDGER_FILE, sheet_name=LEDGER_SHEET)
    tds_map_df = pd.read_csv(TDS_MAPPING_FILE)
    tds_rates_df = pd.read_csv(TDS_RATES_FILE)

    hardcoded_df = pd.read_csv(HARDCODED_VENDOR_FILE)
    hardcoded_df["Vendor_clean"] = (
        hardcoded_df["Vendor"].astype(str).str.strip().str.lower()
    )
    hardcoded_map = hardcoded_df.set_index("Vendor_clean").to_dict("index")

    # --- Turnover threshold -------------------------------------------
    logger.info("Turnover > ₹10 crore flag: %s", turnover_gt_10cr)

    # --- Ledger PAN Mapping -------------------------------------------
    ledger_df.columns = ledger_df.columns.str.strip().str.lower()
    ledger_df["ledger name"] = (
        ledger_df["$name"].astype(str).str.strip().str.lower().str.replace(" ", "")
    )
    ledger_df["pan_raw"] = ledger_df["$incometaxnumber"].astype(str).str.strip()
    ledger_df["gstin"] = ledger_df["$partygstin"].astype(str).str.strip()

    def extract_valid_pan(row):
        pan = row["pan_raw"]
        if pan and sum(c.isdigit() for c in pan) >= 4:
            return pan
        gstin = row["gstin"]
        if gstin and len(gstin) >= 12:
            possible_pan = gstin[2:12]
            if sum(c.isdigit() for c in possible_pan) >= 4:
                return possible_pan
        return "PAN not found"

    ledger_df["final_pan"] = ledger_df.apply(extract_valid_pan, axis=1)
    ledger_pan_map = dict(zip(ledger_df["ledger name"], ledger_df["final_pan"]))

    # --- TDS Section Mapping ------------------------------------------
    if "Ledger_norm" not in tds_map_df.columns:  # backward‑compat
        tds_map_df["Ledger_norm"] = tds_map_df["Ledger"].apply(_normalize)

    tds_section_map = dict(
        zip(tds_map_df["Ledger_norm"], tds_map_df["TDS Section"].fillna("NA"))
    )

    # --- Clean Daybook -------------------------------------------------

    daybook_df["$LedgerName_norm"] = daybook_df["$LedgerName"].apply(_normalize)

    daybook_df["$Party_LedName_clean"] = (
        daybook_df["$Party_LedName"].astype(str).str.strip().str.lower()
    )
    daybook_df["$Led_Group_clean"] = (
        daybook_df["$Led_Group"].astype(str).str.strip().str.lower()
    )
    daybook_df["Month"] = pd.to_datetime(daybook_df["$Date"]).dt.strftime("%b-%y")
    daybook_df["AbsAmount"] = daybook_df["$Amount"].abs()

    grouped = daybook_df.groupby("$Key")

    final_rows = []
    discrepancies_unassigned = []
    discrepancies_missing_pan: set[str] = set()
    discrepancies_multi_creditors = []

    # --- Row processing ------------------------------------------------
    logger.info("Iterating through %d voucher keys…", len(grouped))
    for key, group in grouped:
        expense_rows = group[group["$Led_Group"].isin(GROUP_FILTER)]
        creditor_rows = group[
            group["$Led_Group_clean"].isin(["sundry creditors", "unsecured loans"])
        ]

        if len(creditor_rows) > 1:
            discrepancies_multi_creditors.append(group)

        for _, row in expense_rows.iterrows():
            ledger_name = row["$LedgerName"]
            ledger_norm = row["$LedgerName_norm"]
            month = row["Month"]
            amount = -row["$Amount"]  # keep sign
            narration = row.get("$Narration", "")
            vtype = row.get("$VoucherTypeName", "")
            ledger_group = row["$Led_Group"]

            vendor = (
                row["$Party_LedName"]
                if pd.notna(row["$Party_LedName"]) and row["$Party_LedName"].strip()
                else "Unassigned"
            )
            if vendor == "Unassigned":
                creditor_row = creditor_rows
                if not creditor_row.empty:
                    vendor = creditor_row.iloc[0]["$LedgerName"]
                else:
                    discrepancies_unassigned.append(
                        {
                            "Key": key,
                            "Ledger": ledger_name,
                            "Voucher Type": vtype,
                            "Narration": narration,
                        }
                    )

            pan_key = str(vendor).strip().lower().replace(" ", "")
            pan = ledger_pan_map.get(pan_key, "PAN not found")
            if pan == "PAN not found":
                discrepancies_missing_pan.add(vendor)

            tds_section = tds_section_map.get(ledger_norm, "NA")
            if tds_section == "194Q" and not turnover_gt_10cr:
                tds_section = "NA"

            final_rows.append(
                {
                    "Ledger": ledger_name,
                    "Vendor Associated": vendor,
                    "PAN": pan,
                    "Month": month,
                    "Amount": amount,
                    "Key": key,
                    "Voucher Type": vtype,
                    "Narration": narration,
                    "Ledger Group": ledger_group,
                    "TDS Section": tds_section,
                }
            )

    processed_df = pd.DataFrame(final_rows)

    # ------------------------------------------------------------------
    # SECTION overrides & rates (logic unchanged)
    # ------------------------------------------------------------------
    def _section_override(row):
        v = str(row["Vendor Associated"]).strip().lower()
        if v in hardcoded_map:
            sec = str(hardcoded_map[v].get("TDS Section", "")).strip()
            if sec:
                row["TDS Section"] = sec
        return row

    processed_df = processed_df.apply(_section_override, axis=1)

    processed_df["PAN_trimmed"] = processed_df["PAN"].str.strip().str.upper()
    processed_df["PAN_type"] = processed_df["PAN_trimmed"].apply(
        lambda x: x[3] if len(x) >= 4 else ""
    )

    tds_rates_df["Section"] = tds_rates_df["Section"].astype(str).str.strip()
    tds_rates_df["Limit 1"] = pd.to_numeric(
        tds_rates_df["Limit 1"], errors="coerce"
    ).fillna(0)
    tds_rates_df["Limit 2"] = pd.to_numeric(tds_rates_df["Limit 2"], errors="coerce")
    tds_rates_df["Rate (Individual)"] = pd.to_numeric(
        tds_rates_df["Rate for individual"], errors="coerce"
    ).fillna(0)
    tds_rates_df["Rate (Other)"] = pd.to_numeric(
        tds_rates_df["Rate"], errors="coerce"
    ).fillna(0)

    vendor_totals = (
        processed_df[processed_df["TDS Section"] != "NA"]
        .groupby(["Vendor Associated", "TDS Section"])["Amount"]
        .sum()
        .reset_index()
        .rename(columns={"Amount": "Total_Vendor_Amount"})
    )

    processed_df = processed_df.merge(
        vendor_totals, on=["Vendor Associated", "TDS Section"], how="left"
    )

    processed_df = processed_df.merge(
        tds_rates_df[
            ["Section", "Limit 1", "Limit 2", "Rate (Individual)", "Rate (Other)"]
        ],
        left_on="TDS Section",
        right_on="Section",
        how="left",
    )

    processed_df["Limit 1"] = processed_df["Limit 1"].fillna(0)
    processed_df["Rate (Individual)"] = processed_df["Rate (Individual)"].fillna(0)
    processed_df["Rate (Other)"] = processed_df["Rate (Other)"].fillna(0)

    # helper: round away from zero
    def _round_away(x):
        return int(x + 0.9999) if x >= 0 else int(x - 0.9999)

    def compute_applicability(row):
        section = str(row["TDS Section"]).strip().upper()
        if section in ["", "NA", "192"]:
            return "No"
        limit1, limit2 = row["Limit 1"], row["Limit 2"]
        total, amount = row["Total_Vendor_Amount"], row["Amount"]
        if abs(total) >= limit1:
            return "Yes"
        if pd.notna(limit2) and abs(amount) >= limit2:
            return "Yes"
        return "No"

    processed_df["TDS Applicable"] = processed_df.apply(compute_applicability, axis=1)

    def compute_rate(row):
        if row["TDS Applicable"] != "Yes":
            return 0
        return (
            row["Rate (Individual)"] if row["PAN_type"] == "P" else row["Rate (Other)"]
        )

    processed_df["TDS Rate"] = processed_df.apply(compute_rate, axis=1)

    # ------------------------------------------------------------------
    # custom TDS amount calc with signed rounding
    # ------------------------------------------------------------------
    def calculate_tds_amounts(df):
        df["TDS Amount"] = 0
        df_194q = df[df["TDS Section"] == "194Q"].copy()
        df_other = df[df["TDS Section"] != "194Q"].copy()

        # 194Q – threshold logic keeps sign of Amount
        if not df_194q.empty:
            df_194q["TxnDate"] = pd.to_datetime(
                df_194q["Month"], format="%b-%y", errors="coerce"
            )
            df_194q.sort_values(
                by=["Vendor Associated", "TxnDate", "Row No"], inplace=True
            )
            vendor_cum, computed_rows = {}, []
            for _, r in df_194q.iterrows():
                v, amt, rate, app = (
                    r["Vendor Associated"],
                    r["Amount"],
                    r["TDS Rate"],
                    r["TDS Applicable"],
                )
                cum = vendor_cum.get(v, 0)
                tds_amt = 0
                if app == "Yes":
                    if abs(cum) >= 50_00_000:
                        tds_amt = amt * rate / 100
                    elif abs(cum) + abs(amt) > 50_00_000:
                        excess = abs(cum) + abs(amt) - 50_00_000
                        tds_amt = np.sign(amt) * excess * rate / 100
                rd = r.to_dict()
                rd["TDS Amount"] = _round_away(tds_amt)
                vendor_cum[v] = cum + amt
                computed_rows.append(rd)
            df_194q = pd.DataFrame(computed_rows)

        # All other sections – simple sign‑aware calculation
        df_other["TDS Amount"] = df_other.apply(
            lambda r: (
                _round_away(r["Amount"] * r["TDS Rate"] / 100)
                if r["TDS Applicable"] == "Yes"
                else 0
            ),
            axis=1,
        )

        return (
            pd.concat([df_194q, df_other], ignore_index=True).sort_index()
            if not df_194q.empty
            else pd.concat([df_194q, df_other]).sort_index()
        )

    processed_df.insert(0, "Row No", range(1, len(processed_df) + 1))
    processed_df = calculate_tds_amounts(processed_df)

    def applicability_reason(row):
        section = str(row["TDS Section"]).strip().upper()
        if section in ["", "NA", "NONE", "NULL"]:
            return "Section NA"
        if section == "192":
            return "Section 192 - Salary (not applicable)"
        if abs(row["Total_Vendor_Amount"]) >= row["Limit 1"]:
            return "Above Limit 1"
        if pd.notna(row["Limit 2"]) and abs(row["Amount"]) >= row["Limit 2"]:
            return f"Above Limit 2 ({row['Limit 2']})"
        return "Below Limits"

    processed_df["TDS Applicability Reason"] = processed_df.apply(
        applicability_reason, axis=1
    )

    def _apply_final_overrides(row):
        v = str(row["Vendor Associated"]).strip().lower()
        if v in hardcoded_map:
            hc = hardcoded_map[v]
            app_ovr = str(hc.get("TDS Applicable", "")).strip().title()
            if app_ovr in ["Yes", "No"]:
                row["TDS Applicable"] = app_ovr
            reason_txt = str(hc.get("Reason", "")).strip()
            row["TDS Applicability Reason"] = (
                f"Hardcoded - {reason_txt}"
                if reason_txt
                else "Hardcoded - Reason Not Provided"
            )
        return row

    processed_df = processed_df.apply(_apply_final_overrides, axis=1)
    processed_df["TDS Rate"] = processed_df.apply(compute_rate, axis=1)
    processed_df = calculate_tds_amounts(processed_df)

    columns_to_drop = [
        "PAN_trimmed",
        "PAN_type",
        "Section",
        "Limit 1",
        "Limit 2",
        "Rate (Individual)",
        "Rate (Other)",
    ]
    processed_df.drop(columns=columns_to_drop, inplace=True, errors="ignore")

    processed_df.to_excel(OUTPUT_FILE, index=False)
    logger.info("Output written to %s", OUTPUT_FILE)

    with pd.ExcelWriter(DISCREPANCY_FILE, engine="xlsxwriter") as writer:
        if discrepancies_unassigned:
            pd.DataFrame(discrepancies_unassigned).to_excel(
                writer, sheet_name="Unassigned Vendors", index=False
            )

        if discrepancies_missing_pan:
            missing_pan_df = pd.DataFrame(
                sorted(discrepancies_missing_pan), columns=["Vendor"]
            ).drop_duplicates()
            applicable_vendors = (
                processed_df[
                    (processed_df["TDS Applicable"] == "Yes")
                    & (processed_df["PAN"] == "PAN not found")
                ]["Vendor Associated"]
                .str.strip()
                .str.lower()
                .drop_duplicates()
            )
            filtered_missing_pan_df = missing_pan_df[
                missing_pan_df["Vendor"]
                .str.strip()
                .str.lower()
                .isin(applicable_vendors)
            ]
            if not filtered_missing_pan_df.empty:
                filtered_missing_pan_df.to_excel(
                    writer, sheet_name="Missing PAN", index=False
                )

        if discrepancies_multi_creditors:
            pd.concat(discrepancies_multi_creditors).to_excel(
                writer, sheet_name="Multiple Creditors in Key", index=False
            )

    logger.info("Discrepancy report saved to %s", DISCREPANCY_FILE)
    logger.info("%d rows processed. File saved: %s", len(processed_df), OUTPUT_FILE)


# ─── CLI wrapper (unchanged API) ────────────────────────────────────────
def run_step2_cli(
    daybook_file: str | None = None,
    ledger_file: str | None = None,
    turnover_gt_10cr: bool = False,
) -> None:
    """
    Wrapper invoked by `tds-app run-all`.

    It accepts three positional arguments in this order:
        1. daybook_file  – path to Daybook.xlsx  (optional, default constant)
        2. ledger_file   – path to Ledger.xlsx   (optional, default constant)
        3. turnover_gt_10cr – True/False flag

    Calling it with no arguments still works; it just uses the defaults.
    """
    global DAYBOOK_FILE, LEDGER_FILE  # allow runtime override

    if daybook_file is not None:
        DAYBOOK_FILE = daybook_file
    if ledger_file is not None:
        LEDGER_FILE = ledger_file

    run_step2(turnover_gt_10cr=turnover_gt_10cr)


if __name__ == "__main__":
    run_step2()
