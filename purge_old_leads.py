"""
purge_old_leads.py — Export leads from old campaigns to CSV, then delete them.

Frees up uploaded contact slots (25K/month plan limit).
Skips active campaigns (status=1) and the current AutoOpt experiments.

Usage:
  python purge_old_leads.py              # export + delete
  python purge_old_leads.py --dry-run    # export only, don't delete
"""

import os
import csv
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("purge")

BASE_URL = "https://api.instantly.ai/api/v2"
ROOT = Path(__file__).parent
EXPORT_DIR = ROOT / "data" / "exports"
ACTIVE_EXPERIMENTS_FILE = ROOT / "data" / "active_experiments.json"


def headers():
    return {
        "Authorization": f"Bearer {os.environ['INSTANTLY_API_KEY']}",
        "Content-Type": "application/json",
    }


def get_all_campaigns():
    """Fetch all campaigns, paginating if needed."""
    all_campaigns = []
    starting_after = None
    while True:
        params = {"limit": 100}
        if starting_after:
            params["starting_after"] = starting_after
        r = requests.get(f"{BASE_URL}/campaigns", headers=headers(), params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        all_campaigns.extend(items)
        starting_after = data.get("next_starting_after")
        if not starting_after or not items:
            break
    return all_campaigns


def list_leads(campaign_id, limit=100):
    """Paginate through all leads in a campaign."""
    all_leads = []
    starting_after = None
    while True:
        body = {"campaign_id": campaign_id, "limit": limit}
        if starting_after:
            body["starting_after"] = starting_after
        r = requests.post(f"{BASE_URL}/leads/list", headers=headers(), json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        all_leads.extend(items)
        starting_after = data.get("next_starting_after")
        if not starting_after or not items:
            break
    return all_leads


def export_leads_csv(leads, campaign_name, campaign_id):
    """Write leads to a CSV file."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "- _" else "_" for c in campaign_name)[:60]
    filename = EXPORT_DIR / f"{safe_name}_{campaign_id[:8]}.csv"

    fieldnames = ["email", "first_name", "last_name", "company_name", "status",
                  "email_open_count", "email_reply_count", "job_title", "industry",
                  "location", "company_domain"]

    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            payload = lead.get("payload", {}) or {}
            writer.writerow({
                "email": lead.get("email", ""),
                "first_name": lead.get("first_name", ""),
                "last_name": lead.get("last_name", ""),
                "company_name": lead.get("company_name", ""),
                "status": lead.get("status", ""),
                "email_open_count": lead.get("email_open_count", 0),
                "email_reply_count": lead.get("email_reply_count", 0),
                "job_title": payload.get("jobTitle", ""),
                "industry": payload.get("industry", ""),
                "location": payload.get("location", ""),
                "company_domain": lead.get("company_domain", ""),
            })
    return filename


def delete_leads(campaign_id):
    """Bulk delete all leads from a campaign."""
    r = requests.delete(
        f"{BASE_URL}/leads",
        headers=headers(),
        json={"campaign_id": campaign_id},
        timeout=60,
    )
    r.raise_for_status()
    return r.json() if r.text else {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Export only, don't delete")
    args = parser.parse_args()

    # Load active experiment campaign IDs to protect
    protected_ids = set()
    if ACTIVE_EXPERIMENTS_FILE.exists():
        experiments = json.loads(ACTIVE_EXPERIMENTS_FILE.read_text())
        for exp in experiments:
            protected_ids.add(exp.get("baseline_campaign_id"))
            protected_ids.add(exp.get("challenger_campaign_id"))

    campaigns = get_all_campaigns()
    log.info("Found %d total campaigns. %d protected (active experiments).", len(campaigns), len(protected_ids))

    total_exported = 0
    total_deleted = 0

    for c in campaigns:
        cid = c["id"]
        name = c.get("name", "unnamed")
        status = c.get("status", 0)

        # Skip active campaigns and protected experiments
        if status == 1:
            log.info("SKIP (active): %s", name)
            continue
        if cid in protected_ids:
            log.info("SKIP (protected experiment): %s", name)
            continue

        # List leads
        leads = list_leads(cid)
        if not leads:
            continue

        log.info("Campaign: %s | status=%d | %d leads", name, status, len(leads))

        # Export
        filename = export_leads_csv(leads, name, cid)
        log.info("  Exported to %s", filename)
        total_exported += len(leads)

        # Delete
        if not args.dry_run:
            delete_leads(cid)
            log.info("  Deleted %d leads.", len(leads))
            total_deleted += len(leads)

    log.info("=" * 50)
    log.info("Total exported: %d leads", total_exported)
    if args.dry_run:
        log.info("Dry run — no leads deleted. Run without --dry-run to purge.")
    else:
        log.info("Total deleted: %d leads (contact slots freed)", total_deleted)


if __name__ == "__main__":
    main()
