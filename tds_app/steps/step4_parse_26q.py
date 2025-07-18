"""
Step 4 – parse_26q.py
Extracts Month, Vendor, PAN, Section, Amount Paid, TDS Deducted, Challan No.,
Challan Date from 26Q.docx and exports parsed_26Q.xlsx.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from tds_app.config.settings import settings

# ─── logger ─────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ─── Constants (can be overridden by CLI wrapper) ───────────────────────
SOURCE_DOCX = settings.form26q_file
OUTPUT_XLSX = "parsed_26Q.xlsx"
DATE_FMT_IN = "%d-%m-%Y"  # e.g. 30-09-2024 in the doc
MONTH_FMT_OUT = "%b-%y"  # e.g. Sep-24 in the sheet

# --------------------------------------------------------------------- #
#   0. Regex patterns
# --------------------------------------------------------------------- #
SECTION_RGX = re.compile(r"^(\d{3}[A-Z]?)\s*-", re.IGNORECASE)  # 194C -
VENDOR_RGX = re.compile(r"^(.*?)\s*:\s*([A-Z]{5}\d{4}[A-Z])$")  # Vendor : PAN


def safe_float(x: str) -> float:
    """Strip commas/odd minus signs & convert to float."""
    return float(x.replace(",", "").replace("−", "-").strip())


# --------------------------------------------------------------------- #
#   1. Walk paragraphs & tables in natural order
# --------------------------------------------------------------------- #
def iter_blocks(doc: Document):
    """Yield Paragraph / Table in the order they appear in *doc*."""
    for blk in doc.element.body:
        if isinstance(blk, CT_P):
            yield Paragraph(blk, doc)
        elif isinstance(blk, CT_Tbl):
            yield Table(blk, doc)


def run_step4() -> None:
    logger.info("Parsing 26Q: %s", SOURCE_DOCX)
    doc = Document(SOURCE_DOCX)
    rows: list[dict] = []
    section = vendor = pan = None  # running context

    for blk in iter_blocks(doc):
        # -------- SECTION HEADINGS (paragraph) ------------------------ #
        if isinstance(blk, Paragraph):
            text = blk.text.strip()
            m_sec = SECTION_RGX.match(text)
            if m_sec:
                section = m_sec.group(1).upper()
                vendor = pan = None
                continue
            continue  # skip other paragraphs

        # -------- TABLES (vendors + data) ----------------------------- #
        if not isinstance(blk, Table) or section is None:
            continue

        hdr_cells = [c.text.strip() for c in blk.rows[0].cells]
        if "Date of Payment" not in hdr_cells[0]:
            continue  # stray table

        col = {h: i for i, h in enumerate(hdr_cells)}
        idx_pay_date = col["Date of Payment /Credit"]
        idx_amt_paid = col["Amount of Payment /Credit"]
        idx_tds = col["Amount of Tax Deducted"]
        idx_chal_no = col["Challan No."]
        idx_chal_date = col["Challan Date"]

        for r in blk.rows[1:]:
            cells = [c.text.strip() for c in r.cells]

            # Vendor row?
            if len(set(cells)) == 1:
                vm = VENDOR_RGX.match(cells[0])
                if vm:
                    vendor, pan = vm.group(1).strip(), vm.group(2).strip()
                continue

            # Skip totals / blanks
            first = cells[idx_pay_date]
            if not first or first.lower().startswith("total"):
                continue

            try:
                pay_dt = datetime.strptime(first, DATE_FMT_IN)
            except ValueError:
                continue

            rows.append(
                {
                    "Month": pay_dt.strftime(MONTH_FMT_OUT),
                    "Vendor": vendor or "",
                    "PAN": pan or "",
                    "Section": section,
                    "Amount Paid": safe_float(cells[idx_amt_paid]),
                    "TDS Deducted": safe_float(cells[idx_tds]),
                    "Challan No.": cells[idx_chal_no],
                    "Challan Date": cells[idx_chal_date],
                }
            )

    # ----------------------------------------------------------------- #
    #   2. DataFrame + export
    # ----------------------------------------------------------------- #
    df = pd.DataFrame(rows)
    df.to_excel(OUTPUT_XLSX, index=False)
    logger.info("Parsed %d rows → %s", len(df), OUTPUT_XLSX)


# ─── Public wrapper for Typer CLI ───────────────────────────────────────
def run_step4_cli(form26q_file: str = "26Q.docx") -> None:
    """
    Overrides SOURCE_DOCX, then executes Step 4 parser.
    """
    global SOURCE_DOCX
    SOURCE_DOCX = Path(form26q_file)
    run_step4()


if __name__ == "__main__":
    run_step4()
