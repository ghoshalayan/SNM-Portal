"""KPI Studio stage taxonomy (T-902).

Single source of truth for the set of "stages" the agent pipeline
exposes to per-stage model routing. Each stage is a named LLM call
site with its own model assignment in ``KpiSettings.stage_models``.

Why a registry: every roadmap task that adds a new LLM call (T-204
sanity check, T-301 glossary retrieval, T-401 exemplar retrieval,
T-806 PII classifier, etc.) declares its stage here. The settings UI
reads this list to render its routing matrix without per-task UI
changes.

Conventions:

* ``key``         — snake_case, stable, the JSON key in ``stage_models``.
* ``label``       — plain English, shown in the admin UI.
* ``description`` — one-line hint shown as tooltip / subtitle.
* ``order``       — render order in the matrix (low first).
* ``built``       — True if there is actually a code-site that calls
                    ``build_provider_for_stage`` with this key.
                    False stages render greyed-out with a "future task"
                    tag so admins know the column exists but does nothing
                    yet.
"""
from __future__ import annotations

from dataclasses import dataclass


# Stage keys — module constants so the rest of the codebase imports the
# string instead of duplicating it.
STAGE_PREFLIGHT_PLANNER = "preflight_planner"
STAGE_AGENT_DEFAULT = "agent_default"
STAGE_INSIGHT_GENERATOR = "insight_generator"
STAGE_CHART_PICKER = "chart_picker"
STAGE_SANITY_CHECK = "sanity_check"
STAGE_INTENT_CLASSIFIER = "intent_classifier"


@dataclass(frozen=True)
class StageDef:
    key: str
    label: str
    description: str
    order: int
    built: bool


# Authoring order matches the natural pipeline flow (preflight → agent
# → post-execute) and groups future stages at the bottom.
STAGES: list[StageDef] = [
    StageDef(
        key=STAGE_PREFLIGHT_PLANNER,
        label="Pre-flight planner",
        description=(
            "Disambiguates vague user prompts before the SQL agent runs. "
            "Worth a smart model — gets the rest of the pipeline right."
        ),
        order=10,
        built=True,
    ),
    StageDef(
        key=STAGE_AGENT_DEFAULT,
        label="Agent (NL → SQL)",
        description=(
            "The tool-using loop that produces the final SQL. Default "
            "model for every step inside run_agent today; T-902 follow-up "
            "splits this into propose_sql / reflect / utility sub-stages."
        ),
        order=20,
        built=True,
    ),
    StageDef(
        key=STAGE_INSIGHT_GENERATOR,
        label="Insight generator",
        description=(
            "Second LLM pass over the executed result — produces the "
            "one-sentence insight + follow-up recommendations on chat "
            "turns. Cheap model is fine."
        ),
        order=30,
        built=True,
    ),
    StageDef(
        key=STAGE_CHART_PICKER,
        label="Chart picker (LLM-augmented)",
        description=(
            "Future: chart-type suggestion currently runs deterministic "
            "heuristics; this stage activates when chart_picker grows "
            "an LLM fallback for ambiguous result shapes."
        ),
        order=40,
        built=False,
    ),
    StageDef(
        key=STAGE_SANITY_CHECK,
        label="Result sanity check",
        description=(
            "Future (T-204): a cheap LLM cross-check that flags silently-"
            "wrong results (fan-out doubling, magnitude errors). Picks a "
            "small fast model."
        ),
        order=50,
        built=False,
    ),
    StageDef(
        key=STAGE_INTENT_CLASSIFIER,
        label="Intent classifier",
        description=(
            "Future: classify each prompt into a complexity band so the "
            "Pre-flight planner can route to single-shot vs multi-hop "
            "decomposition (T-206). Tiny model."
        ),
        order=60,
        built=False,
    ),
]


# Lookup helpers — exported for the settings API + healthcheck.
STAGE_BY_KEY: dict[str, StageDef] = {s.key: s for s in STAGES}


def all_stage_keys() -> list[str]:
    """Stable order list of every declared stage key."""
    return [s.key for s in sorted(STAGES, key=lambda s: s.order)]


def built_stage_keys() -> list[str]:
    """Only the stages a code-site actually consumes today. Useful for
    health-checks (no point probing a model that nothing will call)."""
    return [s.key for s in STAGES if s.built]
