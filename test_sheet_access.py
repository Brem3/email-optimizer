"""One-off smoke test: read Luxembourg tab + write/clean a test value in column L."""
import json
import os
from datetime import datetime, timezone

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

SHEET_ID = "1DEdUNWuGRGljBjqSoiV6jWo01h86SHj1KjtbNkJ7w04"
TAB_NAME = "Luxembourg"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def main() -> None:
    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    info = json.loads(raw)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    client = gspread.authorize(creds)

    sh = client.open_by_key(SHEET_ID)
    print(f"[ok] opened spreadsheet: {sh.title}")
    print(f"[ok] service account: {info['client_email']}")

    ws = sh.worksheet(TAB_NAME)
    print(f"[ok] opened tab: {ws.title} ({ws.row_count} rows x {ws.col_count} cols)")

    headers = ws.row_values(1)
    print(f"[ok] headers: {headers}")

    sample = ws.get("A2:K4")
    print(f"[ok] sample rows: {len(sample)} read")
    for row in sample:
        print("     ", row[:5])

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    test_value = f"TEST_WRITE:{stamp}"
    ws.update_acell("L2", test_value)
    print(f"[ok] wrote to L2: {test_value}")

    back = ws.acell("L2").value
    assert back == test_value, f"readback mismatch: {back!r}"
    print("[ok] readback matches")

    ws.update_acell("L2", "")
    print("[ok] cleaned L2")

    print("\nALL GOOD — service account + sheet access working.")


if __name__ == "__main__":
    main()
