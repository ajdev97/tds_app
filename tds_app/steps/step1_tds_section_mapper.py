"""
GPT‑based TDS Section Classifier with OpenAI SDK >= 1.0
Handles rate limits, invalid JSON, **no‑dedupe caching**, and persistent mapping.

Changes vs. previous version
----------------------------
* Keep *raw* ledger names in the CSV (never dropped).
* Add hidden column `Ledger_norm` used only for look‑ups.
* Normalisation is **not** used for deduplication; it is only an internal key.
* `update_cache()` simply appends rows – nothing is removed.

Dependencies:
    pip install openai pandas tqdm

Environment:
    set OPENAI_API_KEY=your‑key      (Windows)
    export OPENAI_API_KEY=your‑key   (Linux/Mac)
"""

from __future__ import annotations

import asyncio
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

# ─── Ledger Normalisation (internal key only) ───────────────────────────


def normalize(name: str) -> str:
    """Lower‑case, strip punctuation & collapse spaces (internal key)."""
    s = str(name).strip().lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return " ".join(s.split())


# ─── Caching Utilities ──────────────────────────────────────────────────


def load_cache(path: str | Path = MAPPING_FILE) -> dict[str, str]:
    """Return dict keyed by *normalised* ledger → TDS Section."""
    if not os.path.exists(path):
        return {}

    df = pd.read_csv(path, dtype=str)

    # Backward‑compat: older files may miss the hidden column
    if "Ledger_norm" not in df.columns:
        df["Ledger_norm"] = df["Ledger"].apply(normalize)

    df["TDS Section"] = df["TDS Section"].fillna("NA").replace("", "NA")
    return dict(zip(df["Ledger_norm"], df["TDS Section"]))


def update_cache(new_data: dict[str, str], path: str | Path = MAPPING_FILE) -> None:
    """Append *raw* ledger rows to the cache (no deduplication)."""

    # Build DataFrame from incoming mapping (raw‑ledger → section)
    df_new = pd.DataFrame(
        {
            "Ledger": list(new_data.keys()),
            "TDS Section": list(new_data.values()),
        },
        dtype=str,
    )
    df_new["Ledger_norm"] = df_new["Ledger"].apply(normalize)
    df_new = df_new[["Ledger", "Ledger_norm", "TDS Section"]]

    if os.path.exists(path):
        df_old = pd.read_csv(path, dtype=str)
        # Ensure hidden column exists (for very old files)
        if "Ledger_norm" not in df_old.columns:
            df_old["Ledger_norm"] = df_old["Ledger"].apply(normalize)
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new

    try:
        df.to_csv(path, index=False)
    except PermissionError as exc:
        logger.error(
            "Cannot write to %s. Please close it if open elsewhere. %s", path, exc
        )


# ─── GPT Call (rate‑limited) ────────────────────────────────────────────

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
    # 1. Load Daybook ---------------------------------------------------
    df = pd.read_excel(settings.daybook_file, sheet_name=DAYBOOK_SHEET)
    df = df[df[GROUP_COLUMN].isin(LEDGER_GROUPS_TO_INCLUDE)]
    original_ledgers = df[LEDGER_COLUMN].dropna().unique()

    # 2. Map *normalised* key → first raw spelling ---------------------
    norm_to_raw: dict[str, str] = {}
    for ledger in original_ledgers:
        key = normalize(ledger)
        if key not in norm_to_raw:
            norm_to_raw[key] = ledger

    cached_map = load_cache()
    uncached_norms = [k for k in norm_to_raw if k not in cached_map]
    uncached_raws = [norm_to_raw[k] for k in uncached_norms]

    logger.info("Total ledgers matching group filters : %d", len(norm_to_raw))
    logger.info("Cached already                       : %d", len(cached_map))
    logger.info("Remaining to classify via API       : %d", len(uncached_norms))

    # 3. Classify via GPT ----------------------------------------------
    results_raw: dict[str, str] = {}
    for i in tqdm(range(0, len(uncached_raws), BATCH_SIZE), desc="Classifying via GPT"):
        batch_raw = uncached_raws[i : i + BATCH_SIZE]
        try:
            logger.debug("Fetching from API for batch: %s", batch_raw)
            batch_result = await classify_batch(batch_raw)
            logger.debug("API Response: %s", batch_result)
            results_raw.update(batch_result)  # raw‑ledger → section
        except Exception as exc:  # noqa: BLE001
            logger.error("Batch failed: %s", exc)

    # 4. Update cache (append – no dedupe) -----------------------------
    if results_raw:
        update_cache(results_raw)
        logger.info("%d new entries written to cache.", len(results_raw))

    full_map = load_cache()  # normalised key → section

    # 5. Per‑run export -------------------------------------------------
    export_df = pd.DataFrame(
        [
            {"Ledger": ledger, "TDS Section": full_map.get(normalize(ledger), "NA")}
            for ledger in original_ledgers
        ]
    )
    export_df.to_csv(EXPORT_FILE, index=False)
    logger.info("Exported -> %s", EXPORT_FILE)

    # 6. Mark ‘In Use’ in the cache ------------------------------------
    cache_df = pd.read_csv(MAPPING_FILE, dtype=str)
    if "Ledger_norm" not in cache_df.columns:
        cache_df["Ledger_norm"] = cache_df["Ledger"].apply(normalize)

    run_df = pd.read_csv(EXPORT_FILE, dtype=str)
    run_df["Ledger_norm"] = run_df["Ledger"].apply(normalize)
    used_set = set(run_df["Ledger_norm"])

    cache_df["In Use"] = cache_df["Ledger_norm"].apply(
        lambda x: "Yes" if x in used_set else "No"
    )
    cache_df = cache_df.sort_values(by="In Use", ascending=False)
    cache_df.to_csv(MAPPING_FILE, index=False)


# ─── Public wrapper (called by CLI) ─────────────────────────────────────


def run_step1(daybook_file: str = "Daybook.xlsx") -> None:
    """Thin wrapper used by the Typer CLI."""

    # Dynamically override settings for this invocation
    settings.daybook_file = Path(daybook_file)  # type: ignore[assignment]

    asyncio.run(main())


# ─── Entry Point (manual execution) ─────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(main())
