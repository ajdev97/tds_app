"""
GPT‑based TDS Section Classifier with OpenAI SDK >= 1.0
Handles rate limits, invalid JSON, normalization, and persistent caching.

Dependencies:
    pip install openai pandas tqdm

Environment:
    set OPENAI_API_KEY=your‑key      (Windows)
    export OPENAI_API_KEY=your‑key   (Linux/Mac)
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import re
from pathlib import Path

import pandas as pd
from openai import AsyncOpenAI
from tqdm import tqdm

from tds_app.config.settings import settings

# ─── logger ─────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ─── CONFIG ─────────────────────────────────────────────────────────────
INPUT_FILE = "Daybook.xlsx"  # kept for wrapper backward‑compat
DAYBOOK_SHEET = "A__DayBook"
LEDGER_GROUPS_TO_INCLUDE = [
    "Direct Expenses",
    "Indirect Expenses",
    "Purchase Accounts",
    "Fixed Assets",
]
LEDGER_COLUMN = "$LedgerName"
GROUP_COLUMN = "$Led_Group"

MAPPING_FILE = "tds_section_mapping.csv"  # cache “database”
EXPORT_FILE = "ledger_tds_sections.csv"  # per‑run export
BATCH_SIZE = 10
MAX_TOKENS = 128
MODEL_NAME = "gpt-4o-mini"
WAIT_BETWEEN_REQUESTS = 20  # seconds
# ────────────────────────────────────────────────────────────────────────

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise EnvironmentError("OPENAI_API_KEY is not set.")
client = AsyncOpenAI(api_key=api_key)

SYSTEM_MSG = (
    "You are a chartered accountant specialising in Indian TDS. "
    "Return a valid compact JSON that maps each ledger name below to a TDS section "
    "applicable to it (e.g. 194C, 194Q, NA). DO NOT explain. "
    "Return only valid minified JSON."
)


# ─── Ledger Normalization ───────────────────────────────────────────────
def normalize(name: str) -> str:
    s = str(name).strip().lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return " ".join(s.split())


# ─── Caching Utilities ──────────────────────────────────────────────────
def load_cache(path: str | Path = MAPPING_FILE) -> dict[str, str]:
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path, dtype=str)
    df["TDS Section"] = df["TDS Section"].fillna("NA").replace("", "NA")
    df["Ledger"] = df["Ledger"].apply(normalize)
    return dict(zip(df["Ledger"], df["TDS Section"]))


def update_cache(new_data: dict[str, str], path: str | Path = MAPPING_FILE) -> None:
    existing = load_cache(path)
    merged = {**existing, **new_data}
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Ledger", "TDS Section"])
            writer.writeheader()
            writer.writerows(
                {"Ledger": ledger, "TDS Section": section}
                for ledger, section in merged.items()
            )
    except PermissionError as exc:
        logger.error(
            "Cannot write to %s. Please close it if open elsewhere. %s", path, exc
        )


# ─── GPT Call ───────────────────────────────────────────────────────────
sema = asyncio.Semaphore(1)


async def classify_batch(batch: list[str]) -> dict[str, str]:
    async with sema:
        await asyncio.sleep(WAIT_BETWEEN_REQUESTS)
        prompt = (
            "Identify the correct Indian TDS section applicable to each ledger name.\n"
            + "\n".join(f"- {name}" for name in batch)
        )
        try:
            response = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_MSG},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=MAX_TOKENS,
                temperature=0,
            )
            content = response.choices[0].message.content.strip()
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse JSON:\n{content}") from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"API call failed: {exc}") from exc


# ─── Main Process ───────────────────────────────────────────────────────
async def main() -> None:
    df = pd.read_excel(settings.daybook_file, sheet_name=DAYBOOK_SHEET)
    df = df[df[GROUP_COLUMN].isin(LEDGER_GROUPS_TO_INCLUDE)]
    original_ledgers = df[LEDGER_COLUMN].dropna().unique()
    normalized_ledgers = sorted({normalize(l) for l in original_ledgers})

    cached_map = load_cache()
    uncached = [l for l in normalized_ledgers if l not in cached_map]

    logger.info("Total ledgers matching group filters : %d", len(normalized_ledgers))
    logger.info("Cached already                       : %d", len(cached_map))
    logger.info("Remaining to classify via API       : %d", len(uncached))

    results: dict[str, str] = {}
    for i in tqdm(range(0, len(uncached), BATCH_SIZE), desc="Classifying via GPT"):
        batch = uncached[i : i + BATCH_SIZE]
        try:
            logger.debug("Fetching from API for batch: %s", batch)
            batch_result = await classify_batch(batch)
            logger.debug("API Response: %s", batch_result)
            batch_result = {normalize(k): v for k, v in batch_result.items()}
            results.update(batch_result)
        except Exception as exc:  # noqa: BLE001
            logger.error("Batch failed: %s", exc)

    if results:
        update_cache(results)
        logger.info("%d new entries written to cache.", len(results))

    full_map = load_cache()
    export_df = pd.DataFrame(
        [
            {"Ledger": ledger, "TDS Section": full_map.get(normalize(ledger), "NA")}
            for ledger in original_ledgers
        ]
    )
    export_df.to_csv(EXPORT_FILE, index=False)
    logger.info("Exported -> %s", EXPORT_FILE)

    cache_df = pd.read_csv(MAPPING_FILE, dtype=str)

    run_df = pd.read_csv(EXPORT_FILE, dtype=str)
    run_df["Ledger_norm"] = run_df["Ledger"].apply(normalize)
    used_set = set(run_df["Ledger_norm"])

    cache_df["In Use"] = cache_df["Ledger"].apply(
        lambda x: "Yes" if normalize(x) in used_set else "No"
    )
    cache_df = cache_df.sort_values(by="In Use", ascending=False)
    cache_df.to_csv(MAPPING_FILE, index=False)


# ─── Public wrapper (called by CLI) ─────────────────────────────────────
def run_step1(daybook_file: str = "Daybook.xlsx") -> None:
    """
    Thin wrapper used by the Typer CLI.
    Overrides settings.daybook_file, then runs the async main().
    """
    from pydantic import Field

    # Dynamically override settings for this invocation
    settings.daybook_file = Path(daybook_file)  # type: ignore[assignment]

    asyncio.run(main())


# ─── Entry Point (manual execution) ─────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())
