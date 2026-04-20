"""Google Sheets connector for the Luxembourg lead pool.

Reads from the "Luxembourg" tab of the configured spreadsheet, skips leads
already marked contacted (either in column F of the sheet, or in the local
contacted.db), and marks leads as contacted in both places when drawn.

Column layout (as of 2026-04-18):
  A: First Name  B: Last Name   C: Sexe         D: Email       E: Company Name
  F: Contacté    G: Company Website  H: Full Name  I: LinkedIn  J: Title
  K: Country     L: Employees Count
"""

import json
import os
import random
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

ROOT = Path(__file__).parent
CONTACTED_DB = ROOT / "data" / "contacted.db"

SHEET_ID = "1DEdUNWuGRGljBjqSoiV6jWo01h86SHj1KjtbNkJ7w04"
TAB_NAME = "Luxembourg"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

CONTACTED_COL_LETTER = "F"
CONTACTED_COL_INDEX = 6  # 1-indexed

COL_FIRST_NAME = 0
COL_LAST_NAME = 1
COL_SEXE = 2
COL_EMAIL = 3
COL_COMPANY = 4
COL_CONTACTED = 5
COL_TITLE = 9

_ws_cache = None
_rows_cache: Optional[list[dict]] = None


def _worksheet():
    global _ws_cache
    if _ws_cache is not None:
        return _ws_cache
    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    creds = Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    client = gspread.authorize(creds)
    _ws_cache = client.open_by_key(SHEET_ID).worksheet(TAB_NAME)
    return _ws_cache


def _ensure_db():
    CONTACTED_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CONTACTED_DB))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS contacted ("
        "email TEXT PRIMARY KEY, "
        "experiment_id TEXT NOT NULL, "
        "contacted_at TEXT NOT NULL)"
    )
    conn.commit()
    return conn


def _contacted_emails() -> set[str]:
    conn = _ensure_db()
    rows = conn.execute("SELECT email FROM contacted").fetchall()
    conn.close()
    return {r[0].lower() for r in rows}


def _load_rows(force: bool = False) -> list[dict]:
    """Fetch all Luxembourg rows. Cached per process."""
    global _rows_cache
    if _rows_cache is not None and not force:
        return _rows_cache

    ws = _worksheet()
    all_values = ws.get_all_values()
    if not all_values:
        _rows_cache = []
        return _rows_cache

    rows = []
    for sheet_row_idx, row in enumerate(all_values[1:], start=2):
        padded = row + [""] * (12 - len(row))
        email = padded[COL_EMAIL].strip()
        if not email:
            continue
        rows.append({
            "sheet_row": sheet_row_idx,
            "first_name": padded[COL_FIRST_NAME].strip(),
            "last_name": padded[COL_LAST_NAME].strip(),
            "sexe": padded[COL_SEXE].strip(),
            "email": email,
            "company_name": padded[COL_COMPANY].strip(),
            "contacted": padded[COL_CONTACTED].strip(),
            "title": padded[COL_TITLE].strip(),
        })
    _rows_cache = rows
    return _rows_cache


def _available_rows() -> list[dict]:
    contacted_local = _contacted_emails()
    return [
        r for r in _load_rows()
        if not r["contacted"] and r["email"].lower() not in contacted_local
    ]


def pool_stats() -> dict:
    rows = _load_rows()
    contacted_local = _contacted_emails()
    available = sum(
        1 for r in rows
        if not r["contacted"] and r["email"].lower() not in contacted_local
    )
    marked_in_sheet = sum(1 for r in rows if r["contacted"])
    return {
        "total": len(rows),
        "available": available,
        "assigned": len(rows) - available,
        "marked_in_sheet": marked_in_sheet,
        "contacted_db": len(contacted_local),
    }


def pool_sample(n: int = 15) -> list[dict]:
    avail = _available_rows()
    if not avail:
        return []
    sampled = random.sample(avail, min(n, len(avail)))
    return [
        {
            "job_title": r["title"] or "(no title)",
            "company": r["company_name"] or "(no company)",
            "industry": "",
            "city": "Luxembourg",
            "state": "",
        }
        for r in sampled
    ]


def pool_title_breakdown(top: int = 15) -> list[tuple[str, int]]:
    avail = _available_rows()
    counts = Counter(r["title"] or "(no title)" for r in avail)
    return counts.most_common(top)


def pick_leads(count: int) -> list[dict]:
    """Reserve `count` available leads in memory. Does NOT touch the sheet or DB.

    Caller must call mark_contacted(leads, experiment_id) after the leads are
    successfully uploaded to Instantly. Until then the leads remain available.

    Returns list of lead dicts. Each dict carries an internal `_sheet_row` key
    used by mark_contacted.
    """
    avail = _available_rows()
    if len(avail) < count:
        raise RuntimeError(
            f"Lead pool exhausted: need {count}, only {len(avail)} available. "
            f"Add more leads to the '{TAB_NAME}' tab or reuse contacted ones."
        )
    drawn = random.sample(avail, count)
    return [
        {
            "email": r["email"],
            "first_name": r["first_name"],
            "last_name": r["last_name"],
            "company_name": r["company_name"],
            "Sexe": r["sexe"],
            "_sheet_row": r["sheet_row"],
        }
        for r in drawn
    ]


def mark_contacted(leads: list[dict], experiment_id: str) -> None:
    """Mark leads as contacted: column F in sheet + local DB. Idempotent.

    Call this ONLY after the leads have been successfully handed off to
    Instantly (or any other downstream system). If it's called prematurely,
    the leads are burned — they can't be reused.
    """
    if not leads:
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    marker = f"contacted:{experiment_id}:{stamp}"

    ws = _worksheet()
    cells_to_update = [
        gspread.cell.Cell(row=lead["_sheet_row"], col=CONTACTED_COL_INDEX, value=marker)
        for lead in leads
        if lead.get("_sheet_row")
    ]
    if cells_to_update:
        ws.update_cells(cells_to_update, value_input_option="USER_ENTERED")

    conn = _ensure_db()
    conn.executemany(
        "INSERT OR IGNORE INTO contacted (email, experiment_id, contacted_at) VALUES (?, ?, ?)",
        [(lead["email"], experiment_id, stamp) for lead in leads],
    )
    conn.commit()
    conn.close()


def draw_leads(experiment_id: str, count: int) -> list[dict]:
    """Legacy wrapper: pick + mark in one step. Prefer pick_leads + mark_contacted."""
    leads = pick_leads(count)
    mark_contacted(leads, experiment_id)
    return leads


def reset_cache():
    global _rows_cache, _ws_cache
    _rows_cache = None
    _ws_cache = None


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print("stats:", pool_stats())
    print("top titles:")
    for t, c in pool_title_breakdown(10):
        print(f"  {c:4d}  {t}")
    print("\nsample:")
    for s in pool_sample(5):
        print(" ", s)
