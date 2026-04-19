"""Deploy multiple experiments in one batch.

Usage: python deploy_batch.py --count 10
Each iteration generates a unique challenger via Claude and deploys it.
"""

import sys
import time
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("deploy_batch")

from dotenv import load_dotenv
load_dotenv()

import orchestrator as o

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10, help="Number of experiments to deploy")
    args = parser.parse_args()

    stats = o.pool_stats()
    needed = args.count * 2 * o.LEADS_PER_ARM  # 2 arms per experiment
    log.info("Pool: %d available, need %d for %d experiments", stats["available"], needed, args.count)
    if stats["available"] < needed:
        log.error("Not enough leads! Have %d, need %d. Aborting.", stats["available"], needed)
        sys.exit(1)

    deployed = []
    failed = []

    for i in range(1, args.count + 1):
        log.info("=" * 60)
        log.info("EXPERIMENT %d/%d", i, args.count)
        log.info("=" * 60)
        try:
            # Get current baseline summary (no harvest — just generate + deploy)
            summary = f"Batch deploy {i}/{args.count}. No harvest this round."

            log.info("Generating challenger %d...", i)
            challenger_config = o.phase_generate(summary)

            log.info("Deploying experiment %d...", i)
            baseline_id, challenger_id, b_added, c_added, _ = o.phase_deploy(challenger_config)

            deployed.append({
                "index": i,
                "baseline_id": baseline_id,
                "challenger_id": challenger_id,
                "b_leads": b_added,
                "c_leads": c_added,
            })
            log.info("Experiment %d deployed: B=%s, C=%s (%d+%d leads)",
                     i, baseline_id[:8], challenger_id[:8], b_added, c_added)

            # Brief pause between deploys to avoid experiment_id collision
            if i < args.count:
                time.sleep(5)

        except Exception as e:
            log.exception("Experiment %d failed: %s", i, e)
            failed.append({"index": i, "error": str(e)})

    log.info("=" * 60)
    log.info("BATCH COMPLETE: %d deployed, %d failed", len(deployed), len(failed))
    for d in deployed:
        log.info("  OK: B=%s C=%s (%d+%d leads)", d["baseline_id"][:8], d["challenger_id"][:8], d["b_leads"], d["c_leads"])
    for f in failed:
        log.info("  FAIL #%d: %s", f["index"], f["error"][:100])

    # Final pool stats
    stats = o.pool_stats()
    log.info("Pool remaining: %d available, %d assigned", stats["available"], stats["assigned"])


if __name__ == "__main__":
    main()
