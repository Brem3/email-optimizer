"""
test_parsers.py — Verify parse_lead_filter, parse_email_steps, parse_campaign_settings
against both baseline.md and challenger_preview.md.
"""

import sys
import json
from pathlib import Path

# Add orchestrator directory to path
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import parse_lead_filter, parse_email_steps, parse_campaign_settings

ROOT = Path(__file__).parent
BASELINE_FILE = ROOT / "config" / "baseline.md"
CHALLENGER_FILE = ROOT / "config" / "challenger_preview.md"

SEP = "-" * 60

EXPECTED_LEAD_FIELDS = [
    "contact_location",
    "fetch_count",
]

EXPECTED_STEP_COUNT = 1
EXPECTED_DELAYS = [0]

EXPECTED_SETTINGS = {
    "daily_limit": 60,
    "email_gap": 10,
    "timezone": "Europe/Paris",
    "schedule_start": "09:00",
    "schedule_end": "17:00",
}


def check_lead_filter(name: str, result: dict) -> list:
    """Return list of issues found in parsed lead filter."""
    issues = []
    for field in EXPECTED_LEAD_FIELDS:
        if field not in result:
            issues.append(f"MISSING KEY: '{field}'")
        elif result[field] is None or result[field] == [] or result[field] == "":
            issues.append(f"EMPTY/NULL: '{field}' = {result[field]!r}")
    return issues


def check_email_steps(name: str, steps: list) -> list:
    issues = []
    if len(steps) != EXPECTED_STEP_COUNT:
        issues.append(f"Expected {EXPECTED_STEP_COUNT} steps, got {len(steps)}")
    for i, (step, expected_delay) in enumerate(zip(steps, EXPECTED_DELAYS)):
        if step.get("delay") != expected_delay:
            issues.append(f"Step {i+1}: delay={step.get('delay')!r}, expected {expected_delay}")
        variants = step.get("variants", [])
        if not variants:
            issues.append(f"Step {i+1}: no variants")
            continue
        v = variants[0]
        if not v.get("subject"):
            issues.append(f"Step {i+1}: subject is empty")
        if not v.get("body"):
            issues.append(f"Step {i+1}: body is empty")
        elif not v["body"].strip().startswith("<p>"):
            issues.append(f"Step {i+1}: body does not start with <p> tag (not converted to HTML)")
    return issues


def check_campaign_settings(name: str, result: dict) -> list:
    issues = []
    for key, expected in EXPECTED_SETTINGS.items():
        if key not in result:
            issues.append(f"MISSING KEY: '{key}'")
        elif result[key] != expected:
            issues.append(f"'{key}': got {result[key]!r}, expected {expected!r}")
    return issues


def print_section(title: str):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def run_tests(name: str, config_md: str):
    print_section(f"{name.upper()} — parse_lead_filter")
    lf = parse_lead_filter(config_md)
    print(json.dumps(lf, indent=2))
    lf_issues = check_lead_filter(name, lf)
    if lf_issues:
        print(f"\n  [ISSUES]")
        for issue in lf_issues:
            print(f"    ! {issue}")
    else:
        print("\n  [OK] All expected fields present and non-empty.")

    print_section(f"{name.upper()} — parse_email_steps")
    steps = parse_email_steps(config_md)
    for i, step in enumerate(steps):
        v = step["variants"][0] if step.get("variants") else {}
        print(f"  Step {i+1}: delay={step.get('delay')}, subject={v.get('subject')!r}")
        print(f"    body (first 80 chars): {v.get('body', '')[:80]!r}")
    step_issues = check_email_steps(name, steps)
    if step_issues:
        print(f"\n  [ISSUES]")
        for issue in step_issues:
            print(f"    ! {issue}")
    else:
        print(f"\n  [OK] {len(steps)} steps, correct delays, subjects and HTML bodies present.")

    print_section(f"{name.upper()} — parse_campaign_settings")
    settings = parse_campaign_settings(config_md)
    print(json.dumps(settings, indent=2))
    settings_issues = check_campaign_settings(name, settings)
    if settings_issues:
        print(f"\n  [ISSUES]")
        for issue in settings_issues:
            print(f"    ! {issue}")
    else:
        print(f"\n  [OK] All settings match expected values.")

    return lf, steps, settings, lf_issues + step_issues + settings_issues


def compare_lead_filters(baseline_lf: dict, challenger_lf: dict):
    print_section("COMPARISON — Baseline vs Challenger lead filter")
    for field in EXPECTED_LEAD_FIELDS:
        b_val = baseline_lf.get(field)
        c_val = challenger_lf.get(field)
        if b_val != c_val:
            b_empty = not b_val
            c_empty = not c_val
            status = "PRESENT in baseline, MISSING/EMPTY in challenger" if (b_val and c_empty) else "DIFFERS"
            print(f"  [{status}] '{field}':")
            print(f"    baseline:   {b_val!r}")
            print(f"    challenger: {c_val!r}")
    # Fields identical
    identical = [f for f in EXPECTED_LEAD_FIELDS if baseline_lf.get(f) == challenger_lf.get(f)]
    if identical:
        print(f"\n  Fields identical in both: {identical}")


def main():
    baseline_md = BASELINE_FILE.read_text()
    challenger_md = CHALLENGER_FILE.read_text()

    print("=" * 60)
    print("  EMAIL OPTIMIZER — PARSER TESTS")
    print("=" * 60)

    baseline_lf, baseline_steps, baseline_settings, baseline_issues = run_tests("baseline", baseline_md)
    challenger_lf, challenger_steps, challenger_settings, challenger_issues = run_tests("challenger", challenger_md)

    compare_lead_filters(baseline_lf, challenger_lf)

    print_section("SUMMARY")
    print(f"  Baseline issues:   {len(baseline_issues)}")
    for i in baseline_issues:
        print(f"    ! {i}")
    print(f"  Challenger issues: {len(challenger_issues)}")
    for i in challenger_issues:
        print(f"    ! {i}")

    total = len(baseline_issues) + len(challenger_issues)
    print(f"\n  Total issues: {total}")
    if total == 0:
        print("  All parsers passed.")
    else:
        print("  Fix the issues above before deploying.")


if __name__ == "__main__":
    main()
