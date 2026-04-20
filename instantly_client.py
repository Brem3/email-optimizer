"""
Thin wrapper around Instantly API v2.
All methods return raw response dicts. Caller handles errors.

Verified endpoints (March 2026):
- POST /api/v2/campaigns — create campaign
- POST /api/v2/campaigns/{id}/activate — body: {"status": 1}
- POST /api/v2/campaigns/{id}/pause — body: {}
- GET  /api/v2/campaigns/analytics?id={id} — returns [] or [analytics_obj]
- POST /api/v2/leads/add — bulk add up to 1000 leads per request
- POST /api/v2/leads — single lead (deprecated, use bulk)
- GET  /api/v2/accounts — paginated list of sending accounts

- DELETE /api/v2/campaigns/{id} — delete campaign
- DELETE /api/v2/leads — bulk delete leads from a campaign (frees contact upload slots)
- GET  /api/v2/accounts — paginated list of sending accounts (status=1 means active)
Account-campaign mapping: use email_list field on POST /api/v2/campaigns to assign sending accounts.
"""

import os
import time
import logging
import requests

BASE_URL = "https://api.instantly.ai/api/v2"
log = logging.getLogger(__name__)


def _headers():
    return {
        "Authorization": f"Bearer {os.environ['INSTANTLY_API_KEY']}",
        "Content-Type": "application/json",
    }


def _get(path, params=None, retries=3):
    for attempt in range(retries):
        r = requests.get(f"{BASE_URL}{path}", headers=_headers(), params=params, timeout=30)
        if r.status_code == 429:
            log.warning("Rate limited on GET %s, waiting 30s (attempt %d)", path, attempt + 1)
            time.sleep(30)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"GET {path} failed after {retries} retries (429)")


def _post(path, payload, retries=3):
    for attempt in range(retries):
        r = requests.post(f"{BASE_URL}{path}", headers=_headers(), json=payload, timeout=60)
        if r.status_code == 429:
            log.warning("Rate limited on POST %s, waiting 30s (attempt %d)", path, attempt + 1)
            time.sleep(30)
            continue
        if not r.ok:
            log.error("POST %s → %d: %s", path, r.status_code, r.text[:1000])
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"POST {path} failed after {retries} retries (429)")


# --- Accounts ---

def get_active_sending_accounts() -> list:
    """GET /api/v2/accounts — return emails of all active (status=1) accounts."""
    all_emails = []
    starting_after = None
    while True:
        params = {"limit": 100}
        if starting_after:
            params["starting_after"] = starting_after
        data = _get("/accounts", params=params)
        items = data.get("items", [])
        all_emails.extend(a["email"] for a in items if a.get("status") == 1)
        starting_after = data.get("next_starting_after")
        if not starting_after or not items:
            break
    return all_emails


# --- Campaigns ---

def create_campaign(name, sequences, schedule, daily_limit=50, email_gap=10, email_list=None):
    """POST /api/v2/campaigns — returns created campaign with id.

    email_list: list of sending account emails to assign. If None, fetches all
    active accounts (status=1) and assigns them automatically.
    """
    from datetime import datetime, timedelta
    start = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    if email_list is None:
        email_list = get_active_sending_accounts()
        log.info("Auto-assigned %d sending accounts to campaign", len(email_list))

    payload = {
        "name": name,
        "sequences": sequences,
        "campaign_schedule": {
            "start_date": start,
            "end_date": end,
            "schedules": [schedule],
        },
        "email_gap": email_gap,
        "daily_limit": daily_limit,
        "email_list": email_list,
        "stop_on_reply": True,
        "stop_on_auto_reply": True,
        "link_tracking": False,
        "open_tracking": False,
        "text_only": False,
    }
    return _post("/campaigns", payload)


def activate_campaign(campaign_id):
    """POST /api/v2/campaigns/{id}/activate with {"status": 1}"""
    return _post(f"/campaigns/{campaign_id}/activate", {"status": 1})


def pause_campaign(campaign_id):
    """POST /api/v2/campaigns/{id}/pause with {}"""
    return _post(f"/campaigns/{campaign_id}/pause", {})


def delete_campaign(campaign_id):
    """DELETE /api/v2/campaigns/{id}"""
    # Must NOT send Content-Type header on DELETE — Instantly rejects it
    h = {"Authorization": _headers()["Authorization"]}
    r = requests.delete(f"{BASE_URL}/campaigns/{campaign_id}", headers=h, timeout=30)
    r.raise_for_status()
    return r.json() if r.text else {}


def delete_leads_from_campaign(campaign_id):
    """DELETE /api/v2/leads — bulk delete all leads from a campaign.

    Frees up uploaded contact slots on the plan (25K/month limit).
    """
    import requests as req
    r = req.delete(
        f"{BASE_URL}/leads",
        headers=_headers(),
        json={"campaign_id": campaign_id},
        timeout=60,
    )
    r.raise_for_status()
    return r.json() if r.text else {}


def get_analytics(campaign_id):
    """
    GET /api/v2/campaigns/analytics?id={campaign_id}
    Returns dict with: emails_sent_count, reply_count, etc.
    Returns empty dict if no data.
    """
    result = _get("/campaigns/analytics", params={"id": campaign_id})
    if isinstance(result, list):
        return result[0] if result else {}
    return result


def get_campaign(campaign_id):
    """GET /api/v2/campaigns/{id} — returns campaign object with status, name, etc."""
    return _get(f"/campaigns/{campaign_id}")


def delete_campaign_leads(campaign_id):
    """DELETE /api/v2/leads — remove all leads from a campaign (batched, 50/request)."""
    total = 0
    while True:
        r = requests.delete(
            f"{BASE_URL}/leads", headers=_headers(),
            json={"campaign_id": campaign_id, "delete_all_from_campaign": True},
            timeout=60,
        )
        r.raise_for_status()
        count = r.json().get("count", 0)
        total += count
        if count == 0:
            break
        time.sleep(0.3)
    log.info("Deleted %d leads from campaign %s", total, campaign_id)
    return total


# --- Leads ---

BULK_BATCH_SIZE = 1000  # API max per request


def add_leads(campaign_id, leads):
    """
    Add leads to campaign via POST /api/v2/leads/add (bulk endpoint).
    Accepts up to 1000 leads per request. Batches automatically.
    Returns total count of successfully added leads.
    """
    total = len(leads)
    if total == 0:
        return 0

    total_added = 0
    STANDARD_FIELDS = {"email", "first_name", "last_name", "company_name", "phone", "website", "personalization"}
    for i in range(0, total, BULK_BATCH_SIZE):
        batch = leads[i : i + BULK_BATCH_SIZE]
        lead_objects = []
        for lead in batch:
            obj = {"email": lead["email"]}
            custom = {}
            for k, v in lead.items():
                if not v:
                    continue
                if k == "email":
                    continue
                if k in STANDARD_FIELDS:
                    obj[k] = v
                else:
                    custom[k] = v
            if custom:
                obj["custom_variables"] = custom
            lead_objects.append(obj)

        payload = {
            "campaign_id": campaign_id,
            "leads": lead_objects,
            "skip_if_in_workspace": False,
        }
        result = _post("/leads/add", payload)
        added = result.get("upload_count", len(batch))
        total_added += added
        log.info("Bulk upload batch %d-%d: %d added", i + 1, i + len(batch), added)

    log.info("Added %d/%d leads to campaign %s", total_added, total, campaign_id)
    return total_added
