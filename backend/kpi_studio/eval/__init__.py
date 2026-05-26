"""KPI Studio eval harness (T-001).

Runs golden test cases through the full NL→SQL pipeline (preflight →
agent → safety → execute) and records pass/fail per case. CI uses the
pass-rate delta as a regression signal.

Public surface:

* ``runner.run_eval(...)`` — entry point. Loads active cases, fires the
  pipeline, persists results, returns a summary.
* ``cli`` — ``python -m kpi_studio.eval run [...]``.

Cases are authored manually (or auto-promoted from chat history once
T-401 lands). The framework is intentionally seed-empty: the team owns
defining what "golden" means for their KPIs.
"""
from kpi_studio.eval.runner import EvalSummary, run_eval

__all__ = ["EvalSummary", "run_eval"]
