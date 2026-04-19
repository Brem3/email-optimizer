# Email Optimizer — Autonomous Cold Email A/B Testing

An autonomous cold email optimization system inspired by Karpathy's autoresearch pattern. Runs headless on GitHub Actions cron — no human input needed after setup.

**How it works:** On each cron run: harvest reply rates from experiments old enough to evaluate → Claude generates a challenger (mutated copy) → draw leads from a Google Sheet → deploy baseline + challenger on Instantly → commit results → repeat. The baseline ratchets upward over time as winning challengers get promoted.

Winners are decided using Instantly's native classification (all pulled from `/campaigns/analytics`):
- `bounced_count` is subtracted from `emails_sent_count` to get `delivered`.
- `reply_count_automatic` is subtracted from `reply_count` to get `replies_genuine`.
- `total_opportunities` (replies flagged as positive/qualified, manually or via Instantly's AI) is the primary decision signal.
The winner metric is `rate_opportunity = opportunities / delivered`, with `rate_genuine` as fallback when no experiment has any opportunity yet.

## First-Time Setup

**When this project is opened for the first time, walk the user through setup before doing anything else.** Ask for the following:

### 1. API Keys
Create a `.env` file from `.env.example` and collect:
- **INSTANTLY_API_KEY** — Instantly.ai API v2 bearer token (required)
- **ANTHROPIC_API_KEY** — Anthropic API key for Claude challenger generation (required)
- **GOOGLE_SERVICE_ACCOUNT_JSON** — full JSON of a Google Cloud service account key, on a single line inside single quotes (required — used to read/write the lead sheet)
- **WEBHOOK_URL** — Slack webhook URL for notifications (optional)

### 2. Product/Service Description
Update `data/resource.md` — the "What We Sell" section. Ask the user:
- What product or service are you selling?
- Who is your target customer? (industry, company size, job titles)
- What's your core offer / value proposition?
- Any social proof? (revenue, clients, case studies)

### 3. Baseline Email Copy
Update `config/baseline.md` — the initial email that gets A/B tested. Ask the user:
- What subject line do you want to start with?
- Write the email body (or describe what you want and generate it for them)
- Volume settings: `daily_limit` (per-campaign send rate) and `fetch_count` (leads per arm)

### 4. Cold Email Knowledge (optional)
If the user has cold email course notes, playbooks, or strategy docs, paste them into `data/cold-email-course.md`. This gives Claude richer context for generating challengers.

### 5. Lead Source (Google Sheet)
Leads come from a Google Sheet. The code in `sheets_client.py` is hardcoded for:
- `SHEET_ID = "1DEdUNWuGRGljBjqSoiV6jWo01h86SHj1KjtbNkJ7w04"` (spreadsheet "Prosp12")
- `TAB_NAME = "Luxembourg"`
- Column layout: A=First Name, B=Last Name, C=Sexe, D=Email, E=Company Name, F=Contacté, G=Website, H=Full Name, I=LinkedIn, J=Title, K=Country, L=Employees Count

To target a different sheet/tab, edit the constants at the top of `sheets_client.py`. The sheet must be shared with the service account email in **Editor** mode so the code can mark leads as contacted in column F.

### 6. GitHub Actions (for autonomous operation)
The workflow at `.github/workflows/optimize.yml` runs on a cron schedule. The user needs to:
- Push this repo to GitHub
- Add secrets: `INSTANTLY_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `WEBHOOK_URL`
- Enable GitHub Actions
- Make sure `data/contacted.db` is committed (it's tiny) so dedup state persists across runs

## Architecture

```
orchestrator.py          — Main 3-phase loop (harvest → generate → deploy)
instantly_client.py      — Instantly API v2 wrapper
sheets_client.py         — Google Sheets connector (read Luxembourg tab, mark contacted)
deploy_batch.py          — Deploy multiple experiments at once
export_campaigns.py      — Archive all campaigns to JSON + CSV
purge_old_leads.py       — Free contact slots by exporting + deleting old leads
test_parsers.py          — Verify config parsers work correctly
test_sheet_access.py     — One-off smoke test for service account + sheet access

config/baseline.md       — The single file being mutated (current best email)
data/resource.md         — Product context + cold email strategy (read-only reference)
data/cold-email-course.md — Optional cold email knowledge base
data/active_experiments.json — Currently running experiments
data/contacted.db        — Dedup DB (never re-email anyone)
results/results.log      — Append-only JSONL experiment history
results/experiments/     — Full experiment records (copy + configs + results)
```

## Key Concepts

- **Baseline vs Challenger:** Each experiment deploys two campaigns — the current best (baseline) and a Claude-generated mutation (challenger). Metrics are compared after `HARVEST_WINDOW_HOURS` (currently 120h = 5 days). If the challenger wins on `rate_opportunity`, it becomes the new baseline.
- **240 leads/arm:** Each campaign gets 240 leads, sends at 60/day, so all leads are contacted within 4 days. Harvest at day 5 gives late replies time to land.
- **Copy-only mutations:** Claude changes subject lines, body copy, tone, CTA — but lead filters and campaign settings stay constant for experimental control.
- **Opportunity rate (primary metric):** Computed entirely from Instantly's native analytics — no regex, no classification heuristics. `delivered = emails_sent_count - bounced_count` (strips undeliverables from the denominator). `rate_opportunity = total_opportunities / delivered`, where `total_opportunities` is Instantly's count of replies flagged as positive/qualified (manually or by Instantly's AI). Fallback `rate_genuine = (reply_count - reply_count_automatic) / delivered` is used only when neither arm has any opportunity yet.
- **Dedup:** Two-layer — (1) `data/contacted.db` local SQLite, (2) column F "Contacté" in the Luxembourg sheet. The local DB is the source of truth; the sheet column is a visual audit log.

## Safety Rules

- **NEVER delete Instantly campaigns** without explicit user confirmation. The API sometimes returns stale analytics — that doesn't mean campaigns are broken.
- **NEVER overwrite** `active_experiments.json`, `results/results.log`, or `data/contacted.db` — these are irreplaceable experiment data.
- **NEVER pause active campaigns** unless there's a validated safety issue.
- **NEVER clear column F** of the Luxembourg sheet in bulk — it's the visual record of who's been contacted.
