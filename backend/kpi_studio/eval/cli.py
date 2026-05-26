"""``python -m kpi_studio.eval`` — CLI for the eval harness.

Usage examples:

    python -m kpi_studio.eval run
    python -m kpi_studio.eval run --tags critical
    python -m kpi_studio.eval run --tags critical regression
    python -m kpi_studio.eval run --case 12 --case 17
    python -m kpi_studio.eval run --against-snapshot 42
    python -m kpi_studio.eval run --json    # machine-readable output
    python -m kpi_studio.eval list-cases
    python -m kpi_studio.eval seed-starter  # insert 10 starter cases

The CLI exits with:
  0   — every case passed (or no cases configured, with --allow-empty)
  1   — at least one case failed / errored
  2   — invalid invocation / startup error (no provider, no DB)

Designed to be CI-friendly: the runtime parses no .env beyond what the
host already loads, so the same DB connection that the FastAPI app
uses is what the CLI sees.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

# The host application's main.py path-wires up sys.path so kpi_studio is
# importable from inside ``backend/``. When running the CLI we replicate
# that — works whether invoked as ``python -m kpi_studio.eval`` from
# inside backend/ or from the repo root.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(os.path.dirname(_THIS_DIR))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _bootstrap_config():
    """Build a KpiStudioConfig outside of the FastAPI lifecycle.

    Mirrors what ``app.main.create_app`` does — same engine, same
    session factory, same provider resolution — minus the auth dep
    (CLI doesn't authenticate). The auth dep is required by the
    dataclass but never called from the runner, so a no-op suffices.
    """
    from dotenv import load_dotenv
    load_dotenv()

    from app.core.database import SessionLocal, engine as host_engine
    from kpi_studio import KpiStudioConfig
    from kpi_studio.providers.llm.factory import build_provider_from_env

    def _noop_auth():  # pragma: no cover — never invoked from CLI
        raise RuntimeError("auth dep called from CLI context")

    provider = build_provider_from_env(os.environ)

    cfg = KpiStudioConfig(
        auth_dep=_noop_auth,
        metadata_session_factory=SessionLocal,
        target_engine=host_engine,
        tenant_resolver=lambda u: None,
        permission_checker=lambda u, code: True,
        llm_provider=provider,
    )
    return cfg, SessionLocal


def _cmd_run(args: argparse.Namespace) -> int:
    from kpi_studio.eval.runner import run_eval

    cfg, SessionLocal = _bootstrap_config()

    if cfg.llm_provider is None and not args.allow_no_provider:
        _err("No LLM provider configured. Set KPI_LLM_PROVIDER + the "
             "matching key env vars, or pass --allow-no-provider to "
             "see provider_error baselines.")
        return 2

    tags = args.tags or None
    cases = args.case or None
    snapshot = args.against_snapshot

    session = SessionLocal()
    try:
        if not args.json:
            print(f"[eval] starting run (tags={tags or 'all'}, "
                  f"cases={cases or 'all'}, "
                  f"snapshot={snapshot or 'current'})")

        def _stream(outcome):
            if args.json:
                return
            badge = {
                "pass": "PASS",
                "fail": "FAIL",
                "error": "ERR ",
                "skipped": "SKIP",
            }.get(outcome.status, outcome.status.upper())
            extra = ""
            if outcome.failure_reasons:
                extra = "  reasons=" + ",".join(outcome.failure_reasons)
            print(f"  [{badge}] #{outcome.case_id} {outcome.name}{extra}")

        summary = run_eval(
            db=session,
            config=cfg,
            tags=tags,
            case_ids=cases,
            triggered_by="cli",
            against_snapshot_id=snapshot,
            on_case=_stream,
        )

        if args.json:
            payload = {
                "eval_run_id": summary.eval_run_id,
                "cases_total": summary.cases_total,
                "cases_passed": summary.cases_passed,
                "cases_failed": summary.cases_failed,
                "cases_errored": summary.cases_errored,
                "cases_skipped": summary.cases_skipped,
                "pass_rate": summary.pass_rate,
                "started_at": summary.started_at.isoformat(),
                "finished_at": summary.finished_at.isoformat(),
                "outcomes": [
                    {
                        "case_id": o.case_id,
                        "name": o.name,
                        "status": o.status,
                        "failure_reasons": o.failure_reasons,
                        "duration_ms": o.duration_ms,
                    }
                    for o in summary.outcomes
                ],
            }
            print(json.dumps(payload, indent=2))
        else:
            print()
            print(f"[eval] run_id={summary.eval_run_id}  "
                  f"total={summary.cases_total}  "
                  f"pass={summary.cases_passed}  "
                  f"fail={summary.cases_failed}  "
                  f"err={summary.cases_errored}  "
                  f"skip={summary.cases_skipped}  "
                  f"rate={summary.pass_rate * 100:.1f}%")

        # Empty case set: still exit 0 unless the caller passed
        # --require-cases (CI uses this to detect "someone deleted all
        # the cases" misconfigurations).
        if summary.cases_total == 0:
            if args.require_cases:
                _err("No active cases ran. --require-cases is set, failing.")
                return 1
            return 0

        if summary.cases_failed > 0 or summary.cases_errored > 0:
            return 1
        return 0
    finally:
        session.close()


def _cmd_list(args: argparse.Namespace) -> int:
    """``python -m kpi_studio.eval list-cases`` — quick visibility."""
    _bootstrap_config()
    from app.core.database import SessionLocal
    from kpi_studio.models import KpiEvalCase

    session = SessionLocal()
    try:
        q = session.query(KpiEvalCase).order_by(KpiEvalCase.case_id.asc())
        if not args.include_inactive:
            q = q.filter(KpiEvalCase.is_active == True)  # noqa: E712
        rows = q.all()
        if not rows:
            print("(no eval cases — author some via the admin UI or "
                  "POST /api/v1/kpi/eval/cases)")
            return 0
        for row in rows:
            tags = ",".join(row.tags) if row.tags else "-"
            active = "act" if row.is_active else "off"
            print(f"  #{row.case_id:4d}  [{active}]  tags={tags:30s}  {row.name}")
        return 0
    finally:
        session.close()


def _cmd_seed_starter(args: argparse.Namespace) -> int:
    """``python -m kpi_studio.eval seed-starter`` — insert 10 starter cases.

    Idempotent: existing rows (matched by ``name``) are left alone
    unless ``--overwrite`` is passed. New rows are inserted with the
    starter content from ``starter_cases.STARTER_CASES``.
    """
    _bootstrap_config()
    from app.core.database import SessionLocal
    from kpi_studio.models import KpiEvalCase
    from kpi_studio.eval.starter_cases import STARTER_CASES

    session = SessionLocal()
    try:
        inserted = 0
        updated = 0
        skipped = 0
        for case in STARTER_CASES:
            existing = (
                session.query(KpiEvalCase)
                .filter(KpiEvalCase.name == case["name"])
                .first()
            )
            if existing is not None:
                if not args.overwrite:
                    skipped += 1
                    print(f"  [skip] #{existing.case_id} {case['name']} "
                          f"(already exists; use --overwrite to replace)")
                    continue
                # Overwrite mode — update fields in place. Preserves
                # case_id + last_pass_at so the audit trail is intact.
                existing.prompt = case["prompt"]
                existing.expected_tables = case.get("expected_tables")
                existing.expected_columns = case.get("expected_columns")
                existing.expected_row_count_min = case.get("expected_row_count_min")
                existing.expected_row_count_max = case.get("expected_row_count_max")
                existing.golden_sql = case.get("golden_sql")
                existing.strict_tables = case.get("strict_tables", False)
                existing.tags = case.get("tags")
                existing.is_active = True
                updated += 1
                print(f"  [upd]  #{existing.case_id} {case['name']}")
                continue

            row = KpiEvalCase(
                name=case["name"],
                prompt=case["prompt"],
                expected_tables=case.get("expected_tables"),
                expected_columns=case.get("expected_columns"),
                expected_row_count_min=case.get("expected_row_count_min"),
                expected_row_count_max=case.get("expected_row_count_max"),
                golden_sql=case.get("golden_sql"),
                strict_tables=case.get("strict_tables", False),
                tags=case.get("tags"),
                is_active=True,
            )
            session.add(row)
            session.flush()  # so we can print the assigned case_id
            inserted += 1
            print(f"  [new]  #{row.case_id} {case['name']}")

        session.commit()
        print()
        print(f"[seed] done. inserted={inserted}  updated={updated}  "
              f"skipped={skipped}  total_in_set={len(STARTER_CASES)}")
        return 0
    except Exception as e:
        session.rollback()
        _err(f"seed failed: {e}")
        return 2
    finally:
        session.close()


def _err(msg: str) -> None:
    print(f"[eval] ERROR: {msg}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m kpi_studio.eval",
        description="KPI Studio eval harness - fire golden cases through the NL-to-SQL pipeline.",
    )
    sub = p.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="Execute an eval run.")
    p_run.add_argument("--tags", nargs="+", default=None,
                       help="Only run cases whose tags intersect this set.")
    p_run.add_argument("--case", type=int, action="append", default=None,
                       help="Restrict to specific case_ids (repeatable).")
    p_run.add_argument("--against-snapshot", type=int, default=None,
                       help="Force a specific schema_snapshot_id (default: current).")
    p_run.add_argument("--json", action="store_true",
                       help="Emit a machine-readable summary instead of prose.")
    p_run.add_argument("--allow-no-provider", action="store_true",
                       help="Run even when no LLM provider is configured "
                            "(every case will record provider_error).")
    p_run.add_argument("--require-cases", action="store_true",
                       help="Exit 1 when zero cases matched the filter "
                            "(CI guard against 'someone deleted all cases').")

    p_list = sub.add_parser("list-cases", help="List configured cases.")
    p_list.add_argument("--include-inactive", action="store_true",
                        help="Show soft-deleted cases too.")

    p_seed = sub.add_parser(
        "seed-starter",
        help="Insert 10 starter eval cases for the SNM Portal schema.",
    )
    p_seed.add_argument(
        "--overwrite", action="store_true",
        help="Update existing rows whose ``name`` matches the starter "
             "set, instead of skipping them.",
    )

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "run":
        return _cmd_run(args)
    if args.cmd == "list-cases":
        return _cmd_list(args)
    if args.cmd == "seed-starter":
        return _cmd_seed_starter(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
