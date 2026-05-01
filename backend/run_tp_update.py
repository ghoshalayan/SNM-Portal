"""Run the daily TP Cost auto-update.

Schedule this script to run at 12:00 AM IST daily via:
  - Windows Task Scheduler: python run_tp_update.py
  - Linux cron: 0 0 * * * cd /path/to/backend && python run_tp_update.py

What it does:
  For each company, finds RawMaterialCost rows where effectedFrom <= today.
  Updates TPWGST in all QuotDetails belonging to 'Draft' quotations.
  Recalculates totRate, GST, totAmount for each affected row.

Usage:
  python run_tp_update.py                    # All companies
  python run_tp_update.py --company-id 1     # Specific company
"""

import argparse
import sys
import os

# Ensure the app module is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal
from app.services.tp_cost_scheduler import run_tp_cost_update
from app.core.timezone import now_ist


def main():
    parser = argparse.ArgumentParser(description="Daily TP Cost Auto-Update")
    parser.add_argument("--company-id", type=int, default=None,
                        help="Run for specific company (default: all)")
    args = parser.parse_args()

    print(f"[{now_ist()}] Starting TP Cost auto-update...")

    db = SessionLocal()
    try:
        results = run_tp_cost_update(db, company_id=args.company_id)
        for cid, counts in results.items():
            print(f"  Company {cid}: {counts['quot_details']} quotation details updated")
        total = sum(c["quot_details"] for c in results.values())
        print(f"[{now_ist()}] Done. Total rows updated: {total}")
    except Exception as e:
        print(f"[{now_ist()}] ERROR: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
