
from __future__ import annotations

import time
import warnings
from pathlib import Path

import pandas as pd
import pyodbc

from tds_app.config.settings import settings
DSN_NAME = settings.odbc_dsn

# ---------------------------------------------------------------------------
# 1.  Column sets exactly matching your Excel reference exports
# ---------------------------------------------------------------------------
DAYBOOK_COLS = [
    "$Key", "$MasterId", "$AlterID", "$VoucherNumber", "$Date",
    "$VoucherTypeName", "$Led_Lineno", "$Type", "$LedgerName", "$Amount",
    "$Led_Parent", "$Led_Group", "$Party_LedName", "$Vch_GSTIN",
    "$Led_GSTIN", "$Party_GST_Type", "$GST_Classification", "$Narration",
    "$EnteredBy", "$LastEventinVoucher", "$UpdatedDate", "$UpdatedTime",
    "$Nature_Led", "$Led_MID", "$CompanyName", "$Year_from", "$Year_to",
    "$Company_number", "$Path",
]

LEDGER_COLS = [
    "$BankLastImportStmtDate", "$Name", "$IncomeTaxNumber",
    "$GSTRegistrationType", "$Parent", "$PartyGSTIN",
    "$VirtualPaymentAddress", "$BankLastFetchStmtFormat",
    "$DefaultTransferMode", "$DefaultWithdrawVchType",
    "$DefaultDepositVchType", "$DefaultContraVchType",
    "$BankLastFetchBalAcctNum", "$BankPerfectMatchConfig",
    "$DefaultNumSeriesDeposit", "$DefaultNumSeriesWithdrawl",
    "$DefaultNumSeriesInternalTransfer", "$PymtAdvCCEmailIds",
    "$BankIsReconcilePerfectMatches", "$IsPymtAdvOnline",
    "$IsPymtAdvCCEnabled", "$IsIncludePymtAdvBillWise",
    "$BankLastFetchBalance", "$BankLastFetchBalanceDateTime", "Type",
]

DAYBOOK_SQL = f"SELECT {', '.join(DAYBOOK_COLS)} FROM A__DayBook"  # ledger‑line view
LEDGER_SQL  = f"SELECT {', '.join(LEDGER_COLS)}  FROM Ledger"      # ledger master

CHUNKSIZE = 5_000                 # None = fetch all at once


# ---------------------------------------------------------------------------
# Helper to run a SELECT and export to Excel with timer
# ---------------------------------------------------------------------------
def _export(sql: str, outfile: Path, cnxn: pyodbc.Connection, *, chunksize: int | None = None) -> None:
    start = time.perf_counter()

    if chunksize:
        chunks: list[pd.DataFrame] = []
        for chunk in pd.read_sql_query(sql, cnxn, chunksize=chunksize):
            print(f"   › fetched {len(chunk):,} rows …")
            chunks.append(chunk)
        df = pd.concat(chunks, ignore_index=True)
    else:
        df = pd.read_sql_query(sql, cnxn)

    df.to_excel(outfile, index=False)
    elapsed = time.perf_counter() - start
    print(f"✅  {outfile.name}: {len(df):,} rows · {len(df.columns)} cols  ({elapsed:.1f}s)")


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def main() -> None:
    print("🔌  Connecting to Tally ODBC via DSN …")
    cnxn = pyodbc.connect(f"DSN={DSN_NAME};")

    print("\n── Exporting Daybook.xlsx (29 cols) ──")
    _export(DAYBOOK_SQL, Path("Daybook.xlsx"), cnxn, chunksize=CHUNKSIZE)

    print("\n── Exporting Ledger.xlsx (all cols) ──")
    _export(LEDGER_SQL, Path("Ledger.xlsx"), cnxn, chunksize=None)

    cnxn.close()
    print("\n🏁  Done – files ready for the pipeline.")

# --- CLI wrapper -------------------------------------------------------
def run_step0_cli(
    daybook_out: str = "Daybook.xlsx",
    ledger_out: str  = "Ledger.xlsx",
    dsn: str = "TallyODBC64_9000",
) -> None:
    """Public wrapper so cli.py can call this step."""
    global DSN_NAME
    DSN_NAME = dsn
    main()  # same entry point defined earlier

if __name__ == "__main__":
    main()
