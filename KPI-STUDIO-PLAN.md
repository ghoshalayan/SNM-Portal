# KPI Studio — Implementation Plan (revised)

Reusable analytics module structured as **two systems**:
1. **KPI Card Manager** — user-authored, query-driven cards on a drag-drop dashboard.
2. **Smart Analysis Chatbot** — dashboard-embedded chat that talks to the DB and returns charts + narrative + recommendations.

Both systems share an LLM provider abstraction, a SQL safety layer, and a chart auto-picker.

**Created:** 2026-04-28
**Status:** Phase 1 (foundation + introspector) shipped. Schema-explorer page demoted to SuperAdmin-only diagnostic. Awaiting green light on Phase A1.
**Setup:** see [kpisetup.md](kpisetup.md) for env vars and provisioning.
**Existing backlog:** [UPCOMING-FIXES.md](UPCOMING-FIXES.md) (close CRITICAL items first).

---

## Decisions locked in (2026-04-28)

| # | Question | Locked answer |
|---|---|---|
| 1 | Schema explorer page | **Keep behind SuperAdmin** as a diagnostic; introspector kept internal for LLM grounding |
| 2 | Read-only access | New env var **`KPI_DSN`** — defaults to `DB_CONNECTION_STRING` if unset; users point it at a read-only login when ready |
| 3 | First LLM provider | **OpenAI** first (cheapest path to working NL→SQL), **Azure OpenAI** second; OpenAI-compatible interface also covers Cerebras + Ollama Cloud |
| 4 | Dashboard scope | **Both** per-user private dashboards and per-company shared dashboards |
| 5 | Chat history | Keep forever; **rolling-summary compaction** kicks in after every 3 Q&A pairs to control context size |
| 6 | "Save as KPI" from chat | KPI **re-executes live** every render — never frozen results |
| 7 | Auto chart selection | Yes; user can override before saving |

---

## System A — KPI Card Manager

### Author flow
1. User with `kpi:author` permission opens the editor.
2. Writes SQL directly (Phase A1) or generates it from natural language (Phase A3).
3. Hits Run → safety check → executor → result preview.
4. Auto chart picker suggests a type; user accepts or overrides.
5. Save → versioned `kpi_definition` + `kpi_version` rows.

### Dashboard
- **angular-gridster2** for the grid.
- Two modes: **preview** (static) and **edit** (drag-drop reposition + resize).
- Per-card position/size persisted on every drop.
- Two scopes per dashboard: `owner_user_id` (private) or `company_id` (shared, no owner).
- Sharing toggle promotes a private dashboard into the shared scope.

### Auto chart selection (heuristic)
Runs after a query executes; inspects the result:
| Shape | Chosen chart |
|---|---|
| 1 row × 1 number | ScoreCard |
| 1 row × N numbers | Stat group |
| Date column + numeric | Line |
| Single categorical + numeric (≤6 cats) | Bar |
| Single categorical + numeric (≤6 cats, share-of-total semantics) | Pie |
| Two categorical + numeric | Stacked bar / Heatmap |
| Otherwise | Table |

User can override before saving the card.

### CRUD endpoints (Phase A1)
```
GET    /api/v1/kpi/kpis
POST   /api/v1/kpi/kpis
GET    /api/v1/kpi/kpis/{id}
PUT    /api/v1/kpi/kpis/{id}            # creates a new version
DELETE /api/v1/kpi/kpis/{id}            # soft delete
POST   /api/v1/kpi/kpis/preview         # run without saving
POST   /api/v1/kpi/kpis/{id}/run        # re-execute saved KPI live
```

### Dashboard endpoints (Phase A2)
```
GET    /api/v1/kpi/dashboards           # list (mine + shared)
POST   /api/v1/kpi/dashboards
GET    /api/v1/kpi/dashboards/{id}
PUT    /api/v1/kpi/dashboards/{id}      # title / scope
PUT    /api/v1/kpi/dashboards/{id}/layout  # bulk update item positions
POST   /api/v1/kpi/dashboards/{id}/items
DELETE /api/v1/kpi/dashboards/{id}/items/{itemId}
POST   /api/v1/kpi/dashboards/{id}/render  # batch-execute every KPI on the board
```

---

## System B — Smart Analysis Chatbot

### Pipeline per turn
```
user prompt
  → load chat session (with rolling summary if > 3 Q&A)
  → load schema context (cached internal introspection)
  → LLM: generate SQL
  → sql_safety validator
  → read-only executor (timeout + row cap)
  → LLM: analyse result → { narrative, chart_type, chart_config, recommendations }
  → persist message + result to kpi_chat_message
  → return inline render to UI
```

### Surface
- Docked side panel on every dashboard (collapsible).
- Persistent across navigation; `kpi_chat_session` rows per user.
- Each assistant message renders: chart (if applicable) + narrative paragraph + bullet list of recommendations + an action button **"Save as KPI"**.

### Rolling-summary compaction
After every 3 Q&A pairs (6 messages), the older history is summarised into a single system note and original messages are kept on disk but dropped from the LLM context window. Keeps token cost flat regardless of session length.

### Endpoints (Phase B1-B3)
```
GET    /api/v1/kpi/chat/sessions
POST   /api/v1/kpi/chat/sessions
GET    /api/v1/kpi/chat/sessions/{id}/messages
POST   /api/v1/kpi/chat/sessions/{id}/turn   # the main NL→SQL→insight pipeline
DELETE /api/v1/kpi/chat/sessions/{id}
POST   /api/v1/kpi/chat/messages/{id}/save-as-kpi
```

---

## Shared infrastructure

### LLM provider abstraction
```
backend/kpi_studio/providers/llm/
  base.py                 # LlmProvider protocol: complete(), tool_use_loop()
  openai_compatible.py    # Azure OpenAI / Cerebras / Ollama Cloud (one impl, different base_url)
  gemini.py               # google-generativeai SDK
  ms_foundry.py           # azure-ai-inference SDK
  factory.py              # reads KPI_LLM_PROVIDER env var → returns the right impl
```
Selected at runtime by `KPI_LLM_PROVIDER`. Phase A3 wires Azure OpenAI; later phases add the rest.

### SQL safety
- `sqlglot` AST: SELECT-only, deny DDL/DML, deny system schemas, deny `xp_*`/`OPENROWSET`.
- Hard `LIMIT` injected if missing.
- Statement timeout (default 30s) + row cap (default 50k) on the executor.
- Every execution audited to `kpi_query_run`.

### Schema introspector
Already shipped in Phase 1. Now **internal-only** — fed to the LLM as system-prompt context. The HTTP endpoints (`/schema/tables`, `/schema/graph`, `/schema/refresh`) gated behind SuperAdmin for diagnostics.

### Chart auto-picker
Pure function over the result set. Used by both System A (after preview) and System B (after every chat turn).

---

## Phased delivery (revised)

| Phase | Scope | Depends on |
|---|---|---|
| **Phase 1** ✅ | Module skeleton + introspector + schema migration + tests | (none) |
| **A1** | Manual SQL KPIs: editor, sql_safety, executor, scorecard + table + bar + line, KPI CRUD, audit log | Phase 1 |
| **A2** | Dashboards (private + shared), gridster grid, preview/edit modes, layout persistence | A1 |
| **A3** | NL→SQL via `LlmProvider` (OpenAI first, Azure OpenAI second), auto chart selection, "Generate KPI from prompt" path | A1 + OpenAI API key |
| **B1** | Chat UI shell on dashboard, session/message tables, history persistence | A2 |
| **B2** | Wire chat to NL→SQL + executor pipeline; render charts inline; "Save as KPI" action | A3 + B1 |
| **B3** | Insight generation pass (second LLM call: narrative + recommendations); rolling-summary compaction | B2 |

A1 + A2 ship without any LLM dependency — usable immediately.

---

## DB tables (all `kpi_*` prefixed)

| Table | Phase | Purpose |
|---|---|---|
| `kpi_schema_snapshot` | 1 ✅ | Cached introspection (now internal) |
| `kpi_definition` | A1 | KPI metadata; owner; current_version_id |
| `kpi_version` | A1 | Versioned: query, params, chart_type, chart_config |
| `kpi_query_run` | A1 | Audit log: who, when, SQL, duration, row_count, error |
| `kpi_dashboard` | A2 | Dashboards; `scope` ∈ {`user`, `company`}; `owner_user_id` or `company_id` |
| `kpi_dashboard_item` | A2 | KPI version pinned to a dashboard cell with x/y/w/h |
| `kpi_chat_session` | B1 | One row per chat thread; `rolling_summary` text column |
| `kpi_chat_message` | B1 | Each turn; raw + structured payload (chart, narrative, recommendations) |

---

## What changed from the original plan

- ❌ **Schema explorer as a primary feature** — gone from user surface, kept SuperAdmin-only for diagnostics.
- ❌ **Tenant isolation via SQL Server RLS** — descoped. Tenant filtering relies on the `KPI_DSN` user's GRANTs + per-KPI `company_id` ownership. Re-evaluate before A3 if the LLM starts writing cross-tenant queries.
- ❌ **Curated view layer** — descoped for now. The DSN's GRANTs are the boundary.
- ✅ **Smart Analysis Chatbot** added as System B.
- ✅ **Multi-provider LLM** (Azure OpenAI / Foundry / Gemini / Cerebras / Ollama Cloud) — was Anthropic-only before.
- ✅ **Auto chart selection** — was user-only before.
- ✅ **Dual dashboard scope** (private + shared) — was per-user only.

---

## Open prerequisites before A1

1. Close UPCOMING-FIXES CRITICAL items (#1 #2 #4 #23) — committed secrets and DEBUG flag.
2. Decide whether `KPI_DSN` will point at the existing app login or a new read-only login. (Either works — the env var is in place.)
3. Confirm Phase 1 schema-explorer is OK gated behind SuperAdmin (vs. removed entirely).
