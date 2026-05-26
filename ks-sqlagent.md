# KPI Studio — SQL Agent Engineering Reference

**Status:** Phases A1–A7, B1–B2, C, D, F, J, J.2 shipped. Phases B3 (insights, rolling summary), I (auto tenant-filter injection) partially built / future work. **Improvement roadmap: Phase 0 complete** — T-001 (eval harness), T-002 (prompt versioning), T-003 (scheduler), T-004 (provider healthcheck) all shipped 2026-05-23. **T-901 (OpenRouter) + T-902 (per-stage routing) shipped same day. Multi-provider refactor + tabbed settings page shipped 2026-05-25** — see §19.

**Scope of this doc:** Deep dive into the **SQL agent** — the subsystem that turns a natural-language question or stored SQL into a safe, validated query that runs against the target database and feeds dashboards / chat results. Surrounding context (schema explorer, KPI editor, dashboards) is summarised where it touches the agent; full feature docs live alongside their code.

---

## 1. What problem this solves

The SNM Portal has a complex relational schema (25+ tables — quotations, enquiries, customers, lifecycle artefacts) but its built-in screens only show one record at a time. Cross-record analytics — *"top 10 customers by revenue last quarter"*, *"average viability margin by KRO"*, *"PO conversion rate by region"* — historically required custom reports or raw SQL access.

KPI Studio replaces that with a three-tier authoring layer:

| Tier | Author | Surface | How a query is produced |
|---|---|---|---|
| Raw SQL | SuperAdmin | KPI editor | Types T-SQL directly |
| Smart Builder | Author / SuperAdmin | KPI editor (Phase C) | Drags fields into wells; `BuilderSpec` compiles deterministically to SQL |
| Natural Language | Author / Business user | NL→SQL dialog OR chat panel (Phase B) | Prompts the LLM; the **SQL Agent** loops through schema tools, peeks data, validates, and proposes SQL |

Once a query exists (by any of the three paths), it becomes a versioned `KpiVersion` and can be embedded as a tile on a dashboard, run on demand, or drilled into via the chat panel.

**The SQL Agent is the centrepiece of the natural-language path.** The rest of this doc explains how it works end-to-end.

---

## 2. Top-level flow (one user prompt → one chart)

```
                    ┌─────────────────────────────┐
 User prompt ──────►│  Pre-flight Planner         │  Disambiguate vague intent
                    │  ↕ Resolver (Python tools)  │  Ask user if needed
                    └──────────────┬──────────────┘
                                   │ ready=intent
                                   ▼
                    ┌─────────────────────────────┐
 Schema snapshot ──►│  NL→SQL Agent (LLM loop)    │  list_tables / describe_table
                    │  ↕ tool handlers            │  peek_distinct_values
                    │                             │  validate_sql / propose_sql
                    └──────────────┬──────────────┘
                                   │ final SQL + explanation
                                   ▼
                    ┌─────────────────────────────┐
                    │  sql_safety.validate(...)   │  AST parse, denylist, TOP inject
                    └──────────────┬──────────────┘
                                   ▼
                    ┌─────────────────────────────┐
                    │  executor.execute_safe_query│  Bind params, run, audit
                    └──────────────┬──────────────┘
                                   ▼
                    ┌─────────────────────────────┐
                    │  chart_picker.suggest_chart │  Result shape → chart type
                    └──────────────┬──────────────┘
                                   ▼
                    Rows + columns + chart_config
                    persisted to KpiNlRun / KpiChatMessage
```

Every numbered stage is implemented in a single Python module. The next sections walk through each.

---

## 3. Data model

All tables live in the SNM Portal SQL Server database under the `kpi_*` prefix. Source of truth: [backend/kpi_studio/models.py](backend/kpi_studio/models.py).

### 3.1 Schema cache
- **`kpi_schema_snapshot`** — frozen JSON reflection of the target DB. Columns: `snapshot_id`, `database_key`, `payload` (JSON of `{tables: [{name, columns, fks, pks, comment}]}`), `table_count`, `relationship_count`, `is_current`, audit. Created by [w7x8y9z0a1b2_create_kpi_schema_snapshot.py](backend/alembic/versions/w7x8y9z0a1b2_create_kpi_schema_snapshot.py).
- One row per refresh. `is_current = True` marks the active one; older rows kept for history.

### 3.2 KPI authoring
- **`kpi_definition`** — top-level KPI identity. `kpi_id`, `company_id`, `owner_user_id`, `name`, `description`, `current_version_id` (FK), `is_active`, full audit.
- **`kpi_version`** — immutable per-edit snapshot. `version_id`, `kpi_id`, `version_no`, `query_text` (the actual SQL), `database_key`, `chart_config` (JSON), `params_schema` (JSON), `time_column`, `builder_spec` (JSON, Phase C). Created in [x8y9z0a1b2c3_create_kpi_a1_tables.py](backend/alembic/versions/x8y9z0a1b2c3_create_kpi_a1_tables.py); `builder_spec` added in [h4i5j6k7l8m9_add_kpi_version_builder_spec.py](backend/alembic/versions/h4i5j6k7l8m9_add_kpi_version_builder_spec.py); `time_column` in [b2c3d4e5f6h7_add_kpi_version_time_column.py](backend/alembic/versions/b2c3d4e5f6h7_add_kpi_version_time_column.py).
- **`kpi_query_run`** — audit row written on *every* execute (preview, run, chat). `run_id`, `kpi_version_id`, `company_id`, `user_id`, `source` (`preview` / `kpi_run` / `chat`), `query_text` (post-validator), `succeeded`, `error`, `row_count`, `duration_ms`, `truncated`, `started_at`.

### 3.3 NL→SQL audit
- **`kpi_nl_run`** — one row per agent invocation. Adds `prompt`, `final_sql`, `explanation`, `provider`, `model`, `iterations`, `total_tokens`, `duration_ms`, `steps` (full JSON timeline of the tool-call loop), `succeeded`, `error`. Created in [c3d4e5f6h7i8_create_kpi_nl_run.py](backend/alembic/versions/c3d4e5f6h7i8_create_kpi_nl_run.py). Enables replay + debugging.

### 3.4 Chat (Phase B)
- **`kpi_chat_session`** — per-user thread. `chat_session_id`, `company_id`, `user_id`, `title`, `rolling_summary` (Phase B3, unused until summarizer ships), `is_active`. Created in [f6h7i8j9k0l1_create_kpi_chat_tables.py](backend/alembic/versions/f6h7i8j9k0l1_create_kpi_chat_tables.py).
- **`kpi_chat_message`** — one turn. `role` (`user` / `assistant`), `content`, `kind` (`answer` / `clarify`), `sql`, `rewritten_sql`, `result_columns` (JSON), `result_rows` (JSON), `chart_config`, `agent_steps` (JSON), `insight` (Phase B3), `recommendations` (JSON, Phase B3), and the same LLM-metadata fields as `kpi_nl_run`. Phase B3 columns added in [h3i4j5k6l7m8_add_kpi_chat_insight_columns.py](backend/alembic/versions/h3i4j5k6l7m8_add_kpi_chat_insight_columns.py).

### 3.5 Dashboards
- **`kpi_dashboard`** — `name`, `description`, `scope` (`user` / `company`), `owner_user_id`, `company_id`, `is_active`. Created in [y9z0a1b2c3d4_create_kpi_a2_dashboards.py](backend/alembic/versions/y9z0a1b2c3d4_create_kpi_a2_dashboards.py).
- **`kpi_dashboard_item`** — one tile. References `kpi_id` (not `kpi_version_id` — tiles always re-execute the *current* version). Includes Power BI–style coords `grid_x / grid_y / grid_w / grid_h`, plus per-tile overrides `title_override`, `icon`, `animation_in`, `animation_out`, `x_label`, `y_label`, `filters_json`. Grid coords added in [h5i6j7k8l9m0_add_kpi_dashboard_item_grid.py](backend/alembic/versions/h5i6j7k8l9m0_add_kpi_dashboard_item_grid.py).
- **`kpi_dashboard_assignment`** — explicit role/user grants beyond owner + company scope. Created in [b1c2d3e4f5g6_create_kpi_dashboard_assignment.py](backend/alembic/versions/b1c2d3e4f5g6_create_kpi_dashboard_assignment.py).

### 3.6 Relationships, settings
- **`kpi_table_relationship`** — directional FK edges used by Builder + Agent. Columns `from_*`, `to_*`, `cardinality` (`many_to_one` / `one_to_one` / `one_to_many`), `source` (`auto` / `manual`). Created in [h7i8j9k0l1m2_create_kpi_table_relationship.py](backend/alembic/versions/h7i8j9k0l1m2_create_kpi_table_relationship.py).
- **`kpi_settings`** — singleton row, runtime-editable LLM config: `llm_provider`, `openai_api_key`, `openai_model`, `openai_base_url`, `token_budget`, `max_iterations`, `max_tokens_per_call`, `domain_knowledge` (free-form text fed to the LLM as application context), `preflight_enabled`, `preflight_max_rounds`, `preflight_user_escalations`. Created in [d4e5f6h7i8j9_create_kpi_settings.py](backend/alembic/versions/d4e5f6h7i8j9_create_kpi_settings.py); `domain_knowledge` added in [l3m4n5o6p7q8_add_domain_knowledge_to_kpi_settings.py](backend/alembic/versions/l3m4n5o6p7q8_add_domain_knowledge_to_kpi_settings.py).

### 3.7 Tenant & audit
- **Tenant**: `company_id` on every user-owned table. Set on insert from the host's tenant resolver, never mutated.
- **Audit**: `created_at / created_by / updated_at / updated_by` on mutable tables; `created_at / created_by` only on immutable ones (`kpi_version`, `kpi_query_run`, `kpi_nl_run`, `kpi_chat_message`).
- **Soft delete**: `is_active` boolean on definition, dashboard, table_relationship, chat_session.

---

## 4. Schema introspection

The agent never sees raw INFORMATION_SCHEMA — it sees a curated, cached, application-friendly snapshot.

### 4.1 Reflection
[backend/kpi_studio/services/introspector.py](backend/kpi_studio/services/introspector.py)

- `reflect_schema(engine, cfg) → SchemaPayload` uses SQLAlchemy's `Inspector` to walk every table + column + FK + PK on the target connection.
- Filters out system schemas (`sys`, `INFORMATION_SCHEMA`, `master`, `msdb`, `model`, `tempdb`) and excluded table patterns (`alembic_*`, `kpi_*` itself, `sysdiagrams`) per `KpiStudioConfig.excluded_schemas` and `excluded_table_patterns`.
- `persist_snapshot(db, payload, ...)` writes the result as a new `KpiSchemaSnapshot` row, flipping `is_current=True` and unmarking the previous one.
- `get_current_snapshot(db)` is the read-path used by every subsequent agent call.
- `build_graph(payload) → SchemaGraph` derives nodes + edges for the ER-diagram UI.

### 4.2 LLM-facing schema text
[backend/kpi_studio/services/schema_context.py](backend/kpi_studio/services/schema_context.py)

`build_schema_context(payload, max_tables, max_columns_per_table, table_filter) → str` renders the snapshot as compact markdown blocks the model can scan cheaply:

```markdown
### customer
_Master table of all customers_
- id INT [pk]
- name VARCHAR not null
- status VARCHAR not null
- customer_group VARCHAR  → master(group_id)
- created_at DATETIME not null
```

Annotations: `[pk]`, FK arrows `→ table(col)`, nullability. Defaults cap to ~60 tables × 24 columns/table to keep the system prompt under typical token budgets. Larger schemas use `table_filter` driven by the Pre-flight Planner's hints.

### 4.3 Cache TTL
- Snapshot reused for `schema_cache_ttl_seconds` (default 3600s). Configurable via `KPI_SCHEMA_CACHE_TTL_SECONDS`.
- SuperAdmin force-refresh via `POST /api/v1/kpi/schema/refresh`.
- **Caveat:** a freshly added column won't appear until the cache expires or is refreshed; the agent will not see it.

---

## 5. LLM provider layer

The SQL Agent is provider-agnostic — anything that speaks the OpenAI chat-completions tool-use protocol works.

### 5.1 Supported providers
| Key | Default base URL | Default model |
|---|---|---|
| `openai` | `https://api.openai.com/v1` | `gpt-4o-mini` |
| `cerebras` | `https://api.cerebras.ai/v1` | `llama-3.3-70b` |
| `ollama_cloud` | `https://ollama.com/v1` | `llama3.3` |

### 5.2 Resolution order
[backend/kpi_studio/providers/llm/factory.py](backend/kpi_studio/providers/llm/factory.py) — `build_provider_from_env()`:
1. `KpiSettings` DB row (live-editable singleton).
2. Environment variables (`KPI_LLM_PROVIDER`, `KPI_OPENAI_API_KEY`, `KPI_OPENAI_MODEL`, `KPI_OPENAI_BASE_URL`, …).
3. Host-injected `KpiStudioConfig.llm_provider` (test fallback).
- If none of the three yield a usable provider, NL endpoints return `enabled: false` and the chat / generate buttons hide on the frontend.

### 5.3 Protocol
[backend/kpi_studio/providers/llm/base.py](backend/kpi_studio/providers/llm/base.py) defines an SDK-agnostic `LlmProvider` protocol with `complete()` and `complete_with_tools()` methods over normalised `LlmMessage`, `LlmTool`, `LlmToolResult` dataclasses. The current concrete is [openai_compatible.py](backend/kpi_studio/providers/llm/openai_compatible.py) using the `openai` Python SDK. Anthropic SDK is imported as a future option but not wired in yet.

### 5.4 API key handling
- Stored in `kpi_settings.openai_api_key` (plaintext column).
- `GET /api/v1/kpi/settings` returns `has_api_key: bool` only, never the raw value.
- `PUT /api/v1/kpi/settings` accepts a sentinel `KEEP_API_KEY` string in `openai_api_key` to preserve the existing key when other fields are being updated.

---

## 6. Pre-flight Planner (Phase B)

Vague questions ("show me the bad ones") would waste agent iterations. The Pre-flight Planner catches ambiguity *before* the expensive tool-use loop.

### 6.1 The Planner ↔ Resolver loop
[backend/kpi_studio/services/preflight.py](backend/kpi_studio/services/preflight.py) — `run_preflight(provider, schema, user_prompt, domain_knowledge, …) → PreflightVerdict`.

- **Planner**: an LLM that reads the user prompt + the *Domain Knowledge Hub* (free-form text from `kpi_settings.domain_knowledge`, e.g., "An 'enquiry' is created by KROs and moves through Draft → Pending → Approved → Converted") + a compact schema overview.
- **Resolver**: deterministic Python tools the planner can call:
  - `lookup_domain(query)` — keyword-search the domain knowledge blob.
  - `find_table(name_fragment)` — fuzzy-match against snapshot table names.
  - `find_column(table, name_fragment)` — fuzzy-match within a chosen table.
- The Planner either:
  1. **`ready`** → returns a disambiguated `intent` string passed to the NL→SQL Agent.
  2. **`ask_user`** → returns a clarification question; chat persists it as `kind='clarify'` and waits for the next user turn.
  3. **`abort`** → hit `preflight_max_rounds` (default 5, clamped 1..10) without convergence; escalate to user.

### 6.2 Configuration knobs (KpiSettings)
- `preflight_enabled` (default `true`). Set false to skip and feed prompts directly into the agent.
- `preflight_max_rounds` (default 5).
- `preflight_user_escalations` (default 2) — cap on how many `ask_user` rounds in a row before bailing.

---

## 7. The SQL Agent (NL → SQL)

This is the core of the system. It's an iterative tool-use loop, not a single-shot prompt.

### 7.1 Entry points
- **`POST /api/v1/kpi/nl/generate`** ([backend/kpi_studio/api/nl.py](backend/kpi_studio/api/nl.py)) — one-off generation from the KPI editor's "Generate from prompt" dialog. Body: `{ prompt, mode: "agent" | "single" }`. Default mode is `agent`.
- **`POST /api/v1/kpi/chat/sessions/{id}/turn`** ([backend/kpi_studio/api/chat.py](backend/kpi_studio/api/chat.py)) — multi-turn chat panel. Same backend pipeline, plus session history threading and SSE streaming.

### 7.2 Single-shot path (legacy fallback)
[backend/kpi_studio/services/nl2sql.py](backend/kpi_studio/services/nl2sql.py) — `generate_sql(provider, schema, user_prompt, dialect, max_tokens) → Nl2SqlResult`.

One LLM call with a strict system prompt:

> "You write {dialect} SELECT queries for a read-only analytics tool.
> Rules (strict):
> 1. Output **only** a JSON object: `{"sql": "...", "explanation": "..."}`
> 2. The SQL must be a single SELECT statement. No DDL, DML, or system tables.
> 3. Reference only tables and columns that appear in the schema below.
> Schema: …"

Used as `mode: "single"` for cost-sensitive cases. Has a tolerant JSON parser that strips ` ```json ` fences and falls back if the model returns prose.

### 7.3 Agent path (default)
[backend/kpi_studio/services/nl2sql_agent.py](backend/kpi_studio/services/nl2sql_agent.py) — `run_agent(provider, schema, target_engine, db, user_prompt, …) → AgentResult`.

The system prompt opens with:

> "You write {dialect} SELECT queries for a strictly read-only analytics tool.
> You work step-by-step, calling tools to inspect the schema and sample data before proposing a final query."

It receives a tool list and loops:

```python
while iterations < max_iterations and tokens < token_budget:
    response = provider.complete_with_tools(messages, tools)
    if response is final propose_sql tool call:
        break
    for each tool_call in response:
        result = handle_tool(tool_call)
        append (tool_call, result) to messages
    iterations += 1
```

If the model never calls `propose_sql` before caps trip, `AgentResult.error` is set and the surface (chat / generate dialog) shows the partial trace.

### 7.4 The five tools
Defined in [backend/kpi_studio/services/nl2sql_tools.py](backend/kpi_studio/services/nl2sql_tools.py):

| Tool | Signature | What it does |
|---|---|---|
| `list_tables` | `()` | Returns `[{name, comment, column_count}]` from the snapshot. Cheap — no schema sent on first turn. |
| `describe_table` | `(name, schema?)` | Returns full column metadata + PK + FK info for one table. Reads from cached `KpiSchemaSnapshot`. |
| `peek_distinct_values` | `(table, column, limit)` | Live query — `SELECT DISTINCT TOP {limit} {col} FROM {table}`. Routes through `executor.execute_safe_query`. Helps the model see actual values ("status is 'Approved' not 'APPROVED'"). |
| `validate_sql` | `(sql)` | Runs `sql_safety.validate_select_query` without executing. Returns the rewritten SQL + any findings. Lets the model self-correct. |
| `propose_sql` | `(sql, explanation)` | **Terminator.** When the model calls this, the loop exits and the proposal is the agent's final answer. Empty `sql` allowed (covers "you asked for a write, which I can't do"). |

### 7.5 Caps & budgets
All from `kpi_settings`, env, or defaults:
- `max_iterations` (default `8`) — hard limit on tool-call rounds.
- `token_budget` (default `100000`) — cumulative prompt + completion tokens across the whole loop.
- `max_tokens_per_call` (default `4000`) — per-message completion limit.

### 7.6 Domain Knowledge Hub
If `kpi_settings.domain_knowledge` is set, its text is appended to the system prompt before the schema block. This is how the operator teaches the model business semantics that aren't visible in column names ("a `parent code` is the user under whom another user generates quotation numbers", "the FWS lifecycle goes Draft → Approved → locked").

### 7.7 Audit
Every agent run writes a `KpiNlRun` row with the full `steps` JSON (every tool call + response, normalised). This is the replay/debug surface — the editor's "Show agent steps" panel reads it back.

---

## 8. SQL safety layer

Even after the agent proposes SQL, nothing reaches the database without [backend/kpi_studio/services/sql_safety.py](backend/kpi_studio/services/sql_safety.py) approving it.

### 8.1 Function signature
```python
validate_select_query(
    sql: str,
    row_cap: int = 50000,
    dialect: str = "tsql",
) -> SafeQuery  # { original, rewritten, row_cap, notes }
```

### 8.2 What it checks (fail-fast)
1. **Single statement** — `sqlglot.parse(sql)` must return exactly one top-level statement. Multiple `;`-separated payloads rejected.
2. **SELECT-only** — must be `SELECT` or `WITH … SELECT`. DDL (`CREATE`, `ALTER`, `DROP`), DML (`INSERT`, `UPDATE`, `DELETE`, `MERGE`), DCL (`GRANT`, `REVOKE`), TCL (`COMMIT`, `ROLLBACK`) all rejected.
3. **No system schemas** — denylist: `sys`, `INFORMATION_SCHEMA`, `master`, `msdb`, `model`, `tempdb`.
4. **No danger functions** — regex + AST sweep for `xp_*`, `sp_executesql`, `OPENROWSET`, `OPENQUERY`, `OPENDATASOURCE`, `BULK INSERT`.
5. **Parameter whitelist** — only four named binds allowed: `:start_date`, `:end_date`, `:company_id`, `:user_id`. No `?`, no custom names.
6. **Row cap injection** — if the query doesn't already include `TOP N` (SQL Server) or `LIMIT N` (SQLite), the validator rewrites it to inject `TOP {row_cap}` / `LIMIT {row_cap}`. The rewritten SQL is what executes.

### 8.3 Return shape
`SafeQuery { original, rewritten, row_cap, notes }`. If any check fails, raises `SqlSafetyError`. The executor catches and audits as a failed `KpiQueryRun` with the error message.

### 8.4 Findings vs errors
When called from `validate_sql` (the agent's tool), violations are returned as *findings* on the response — non-fatal, the model can iterate. When called from `execute_safe_query`, the same violations raise — the query never runs.

---

## 9. Executor

[backend/kpi_studio/services/executor.py](backend/kpi_studio/services/executor.py) — `execute_safe_query(engine, db, sql, source, ..., bind_params) → ExecutionResult`.

### 9.1 Pipeline
1. `validate_select_query(sql, row_cap, dialect)` → rewritten SQL.
2. `engine.connect()` — pooled SQLAlchemy connection on the **target** engine (separate from the portal's own DB engine — KPI Studio can query a different database).
3. SQL Server: `SET LOCK_TIMEOUT {ms}` for lock-wait protection (best-effort; doesn't help CPU-bound queries).
4. `conn.execute(text(rewritten), bind_params)` where `bind_params` always contains all four reserved names (SQLAlchemy ignores unused ones — safe to over-supply).
5. Fetch columns + rows, stream up to `row_cap`. Truncate beyond.
6. Always write `KpiQueryRun` (success or failure). Capture `duration_ms`, `row_count`, `truncated`, `error`.
7. Return `ExecutionResult { columns, rows, row_count, truncated, duration_ms, rewritten_sql, notes }`.

### 9.2 Tenant binding
The executor's caller (kpi.py / chat.py / nl.py) injects:
```python
bind_params = {
    "start_date": resolved_start,    # from period selector
    "end_date":   resolved_end,
    "company_id": ctx.company_id,    # always the caller's tenant
    "user_id":    ctx.user_id,
}
```
The query author chooses whether to use them. **There is no auto-injection** today — if the SQL doesn't say `WHERE company_id = :company_id`, the query crosses tenants. This is documented and intentional: Phase I will add an opt-in `tenant_resolver` that rewrites the AST to inject the filter on known fact tables.

### 9.3 Guardrails summary

| Guardrail | Default | Configurable |
|---|---|---|
| Row cap | 50,000 | Per call via `row_cap` arg |
| Statement timeout | 30s wall-clock + LOCK_TIMEOUT | Per call |
| Read-only | enforced | No — hard-coded |
| Param whitelist | 4 names | No — hard-coded |
| System schema denylist | hard-coded | No |
| Danger-function denylist | hard-coded | No |

---

## 10. Chart picker

[backend/kpi_studio/services/chart_picker.py](backend/kpi_studio/services/chart_picker.py) — `suggest_chart(columns, rows) → ChartSuggestion`.

Pure heuristic. No ML. Thresholds:
- `PIE_BAR_MAX_CATEGORIES = 6` — if a categorical column has more, falls back to bar/table.
- `LINE_MIN_POINTS = 3` — line chart needs at least 3 datapoints.

Decision tree (simplified):
1. Single row, single numeric column → `scorecard`.
2. Single row, many numeric columns → `stat_group`.
3. Two columns (one categorical, one numeric):
   - Categorical column has a datetime-like name → `line`.
   - Few categories → `pie`.
   - Otherwise → `bar`.
4. Anything else → `table`.

Suggestions are stored on the agent / preview response. The user can override before saving the KPI; thereafter the saved `chart_config` is authoritative.

---

## 11. Chat surface (Phase B)

The chat panel is a thin layer over the agent + executor pipeline.

### 11.1 Session + turn endpoints
[backend/kpi_studio/api/chat.py](backend/kpi_studio/api/chat.py):
- `GET /chat/sessions` — list user's sessions (newest first).
- `POST /chat/sessions` — create empty session.
- `GET /chat/sessions/{id}` — full session detail (all messages).
- `PUT /chat/sessions/{id}` — rename / soft-delete.
- `DELETE /chat/sessions/{id}` — soft-delete.
- **`POST /chat/sessions/{id}/turn`** — send prompt. **Returns a Server-Sent Events stream.** Each step of the agent emits a JSON-serialised `ChatTurnResponse` line; the final line carries the result.
- `POST /chat/sessions/{id}/turn/cancel` — sets a `threading.Event` in the in-memory `_active_turn_cancels` dict keyed by session_id; the running loop polls the event between iterations.

### 11.2 Turn lifecycle
[backend/kpi_studio/services/chat_service.py](backend/kpi_studio/services/chat_service.py) — `run_turn(...)`:
1. Load last N user/assistant pairs from session history via `_load_recent_history()` — gives the model context like "now group by region" referring to the prior SQL.
2. Run Pre-flight Planner. If `ask_user`, persist `kind='clarify'` and return immediately.
3. Run NL→SQL Agent. Stream agent steps as SSE events.
4. Execute the proposed SQL via `execute_safe_query`.
5. Suggest a chart.
6. (Phase B3, stub) `insight_generator.generate_insight(result)` — second LLM pass to surface a one-sentence insight + a small list of follow-up question suggestions. Failure here is non-fatal; the turn still returns.
7. Persist both messages (user + assistant) with all the result fields populated.

### 11.3 Streaming wire format
Each SSE line is a partial `ChatTurnResponse` JSON. The frontend [chat.service.ts](frontend/src/app/features/kpi-studio/services/chat.service.ts) exposes this as an RxJS `Observable<ChatTurnResponse>` so the UI can render step-by-step progress (the "agent is calling describe_table on QuotSummary…" feel).

---

## 12. API surface (full inventory)

All routes are mounted under `/api/v1/kpi/...` by [backend/kpi_studio/router.py](backend/kpi_studio/router.py) and the central API router includes it via `create_router(config)`.

### 12.1 Schema explorer
| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/schema/tables` | `kpi:schema` | Tables + columns from cached snapshot |
| GET | `/schema/graph` | `kpi:schema` | ER diagram nodes + edges |
| POST | `/schema/refresh` | `kpi:schema` | Force re-introspection |
| GET | `/schema/relationships` | `kpi:schema` | Manual + auto FK edges |
| POST | `/schema/relationships/auto-seed` | `kpi:schema` | Seed edges from DB FKs |
| POST | `/schema/relationships` | `kpi:schema` | Add manual edge |
| PUT | `/schema/relationships/{id}` | `kpi:schema` | Toggle active / change cardinality |

### 12.2 KPIs
| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/kpis` | `kpi:view` | List user's + admin KPIs |
| POST | `/kpis` | `kpi:author` | Create definition + initial version |
| GET | `/kpis/{id}` | `kpi:view` | Full detail with version history |
| PUT | `/kpis/{id}` | `kpi:author` | New version on any change to query/chart/spec |
| DELETE | `/kpis/{id}` | `kpi:author` | Soft delete |
| POST | `/kpis/preview` | `kpi:view` | Run unsaved query + suggest chart |
| POST | `/kpis/{id}/run` | `kpi:view` | Re-execute current version |

### 12.3 NL→SQL
| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/nl/status` | `kpi:view` | `{ enabled, provider }` |
| POST | `/nl/generate` | `kpi:author` | Agent (default) or single-shot |
| POST | `/nl/suggest-kpis` | `kpi:author` | Phase J: LLM proposes N KPIs for a table |

### 12.4 Chat
| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/chat/sessions` | `kpi:view` | Newest first |
| POST | `/chat/sessions` | `kpi:author` | New session |
| GET | `/chat/sessions/{id}` | `kpi:view` | With history |
| PUT | `/chat/sessions/{id}` | `kpi:author` | Rename / archive |
| DELETE | `/chat/sessions/{id}` | `kpi:author` | Soft delete |
| POST | `/chat/sessions/{id}/turn` | `kpi:author` | **SSE stream** |
| POST | `/chat/sessions/{id}/turn/cancel` | `kpi:author` | Best-effort cancel |

### 12.5 Dashboards
| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/dashboards` | `kpi:view` | Mine + company + assigned |
| POST | `/dashboards` | `kpi:author` | Create |
| GET | `/dashboards/{id}` | `kpi:view` | With items + assignments |
| PUT | `/dashboards/{id}` | `kpi:author` | Patch metadata |
| DELETE | `/dashboards/{id}` | `kpi:author` | Soft delete |
| POST | `/dashboards/{id}/items` | `kpi:author` | Add tile |
| PUT | `/dashboards/{id}/items/{item_id}` | `kpi:author` | Update tile visual |
| DELETE | `/dashboards/{id}/items/{item_id}` | `kpi:author` | Remove tile |
| PUT | `/dashboards/{id}/layout` | `kpi:author` | Bulk drag-drop reorder |
| POST | `/dashboards/{id}/auto-decorate` | `kpi:author` | Phase J.2: AI visual polish |
| GET | `/dashboards/{id}/assignments` | `kpi:view` | Role/user grants |
| POST | `/dashboards/{id}/assignments` | `kpi:author` | Grant access |
| DELETE | `/dashboards/{id}/assignments/{id}` | `kpi:author` | Revoke |

### 12.6 Settings
| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/settings` | `kpi:admin` | Returns `has_api_key`, never the raw key |
| PUT | `/settings` | `kpi:admin` | `KEEP_API_KEY` sentinel preserves existing key |

### 12.7 Health
| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/healthz` | none | `{ ok: true, llm_provider: "openai" | null }` |

---

## 13. Frontend

[frontend/src/app/features/kpi-studio/](frontend/src/app/features/kpi-studio/)

### 13.1 Folder map
```
kpi-studio/
├── kpi-studio.routes.ts
├── models/schema.types.ts             # TS mirror of backend Pydantic types
├── services/
│   ├── kpi.service.ts                 # CRUD + preview/run
│   ├── nl.service.ts                  # NL→SQL + suggest-kpis
│   ├── dashboard.service.ts           # Dashboard CRUD + items + assignments
│   ├── chat.service.ts                # Chat sessions + SSE turn stream
│   ├── kpi-schema.service.ts          # Schema explorer
│   └── settings.service.ts            # LLM settings
├── shared/                            # error-format, error-banner, value-format
├── components/
│   ├── chart-renderer/                # type → visual mapping
│   ├── chart-style-picker/
│   ├── kpi-builder-pane/              # Phase C drag-drop wells
│   ├── kpi-card/                      # Dashboard tile
│   ├── chat-panel/                    # Message list + input
│   ├── period-selector/
│   ├── generate-prompt-dialog/        # NL→SQL prompt entry
│   ├── suggest-kpis-dialog/           # Phase J KPI suggestions
│   ├── animated-number/
│   └── ...
└── pages/
    ├── kpi-list/
    ├── kpi-editor/                    # SQL + builder + NL surfaces
    ├── dashboards-list/
    ├── dashboard-view/                # Render + edit mode
    ├── schema-explorer/               # SuperAdmin
    ├── settings/                      # SuperAdmin LLM config
    └── chat/                          # Smart-analysis chat page
```

### 13.2 KPI editor
- Left pane: SQL textarea **or** builder wells (Phase C).
- Right pane: result preview table + chart from `ChartRendererComponent`.
- Toolbar:
  - **Generate from prompt** → opens `GeneratePromptDialogComponent` → `nl.service.generate()` → populates the SQL textarea with the agent's proposal + shows validation findings inline.
  - **Run preview** → `kpi.service.preview()` → table + auto-suggested chart.
  - **Save** → new KPI or new version of existing KPI.

### 13.3 Chat page
- Session list on the left, conversation on the right.
- Assistant turns render: explanation prose, SQL block (syntax-highlighted), result preview (table or chart), Phase B3 insight + recommendations (if present), "Save as KPI" button.
- The SSE stream from `runTurn()` updates the assistant bubble in real time as the agent calls each tool — gives the user visibility into *why* the model picked the SQL it did.

### 13.4 Dashboard view
- View mode: tiles laid out on a 12-column grid using `grid_x/y/w/h`. Period selector in the header injects `:start_date / :end_date` into every tile's execute call.
- Edit mode: drag-drop reorder (one bulk `PUT /layout` on drop), resize handles, per-tile overrides dialog (title, icon, animation, axis labels, filters).
- Phase J.2 "Auto-decorate" button: posts to `/auto-decorate`, the LLM proposes per-tile visual polish; the proposal is validated (no coord changes, no overlaps) before being applied.

### 13.5 Schema explorer + settings
SuperAdmin-only. Schema explorer lists tables hierarchically + ER diagram + refresh button + relationship CRUD. Settings page is the LLM config form — provider dropdown, API key (write-only via `KEEP_API_KEY`), model, base URL, token/iteration caps, domain knowledge textarea, preflight knobs.

### 13.6 Routes
```
/kpi-studio
  /dashboards               → DashboardsListComponent
  /dashboards/:id           → DashboardViewComponent (view)
  /dashboards/:id/edit      → DashboardViewComponent (edit)
  /kpis                     → KpiListComponent
  /kpis/new                 → KpiEditorComponent (blank)
  /kpis/:id                 → KpiEditorComponent (load)
  /schema                   → SchemaExplorerComponent (SuperAdmin)
  /settings                 → SettingsComponent (SuperAdmin)
  /chat                     → ChatPageComponent
```
All lazy-loaded standalone components.

---

## 14. Menu & permission integration

### 14.1 Menus
- Parent: **KPI Studio** (icon `insights`).
- Children: **Dashboards** (`space_dashboard`), **KPIs** (`monitoring`), **Schema Explorer** (`schema`, SuperAdmin-gated in code).
- Phase B adds a **Smart Analysis** submenu for chat.
- Seeded per-company by [z0a1b2c3d4e5_add_kpi_studio_menus.py](backend/alembic/versions/z0a1b2c3d4e5_add_kpi_studio_menus.py) (idempotent — safe to re-run). SuperAdmin role automatically gets full CRUD on all KPI Studio menus; other roles must be granted via the role-menu-mapping UI.

### 14.2 Permission codes
| Code | Who | What it gates |
|---|---|---|
| `kpi:view` | Any authenticated user | KPI list, read, status, preview run |
| `kpi:author` | Authors + Admin | Create / edit / delete KPIs, NL→SQL generate, suggest KPIs, dashboard write ops, chat |
| `kpi:schema` | SuperAdmin | Schema explorer + relationship CRUD |
| `kpi:admin` | SuperAdmin | Settings read/write |

These are KPI Studio's *internal* permission codes, separate from `RoleMenuMap`'s `CanAdd/CanRead/CanEdit/CanDelete`. The HTTP route handler decides which `Can*` flag maps to which `kpi:*` code at the boundary.

---

## 15. Technologies

### 15.1 Backend
- **FastAPI 0.115** — routing, dependency injection.
- **SQLAlchemy 2.0** — ORM + `Inspector` for schema reflection.
- **`sqlglot`** — AST parsing for `sql_safety` + builder compilation. Handles T-SQL + SQLite dialects.
- **`openai` SDK** — provider client (also drives Cerebras + Ollama Cloud via OpenAI-compatible endpoints).
- **`anthropic` SDK** — present as a future option, not wired today.
- **`pyodbc`** — SQL Server driver.
- **Alembic** — migrations.
- **No async**, **no Celery**, **no Redis** in Phase 1. Chat streams via SSE on a worker thread; cancellation via `threading.Event`.

### 15.2 Frontend
- **Angular 21** standalone components + signals.
- **Angular Material 21**.
- **RxJS 7.8** — chat SSE stream as Observable, period-selector debouncing.
- **Chart layer** — placeholder; chart renderer is module-pluggable (Vega-Lite / ChartJS to be finalised).
- **No Monaco yet** — KPI editor uses a styled `<textarea>` today; Monaco is the planned drop-in.

### 15.3 Environment variables
```
DB_CONNECTION_STRING=mssql+pyodbc://...        # shared with the host portal
KPI_LLM_PROVIDER=openai|cerebras|ollama_cloud
KPI_OPENAI_API_KEY=...
KPI_OPENAI_MODEL=gpt-4o-mini
KPI_OPENAI_BASE_URL=https://api.openai.com/v1
KPI_TOKEN_BUDGET=100000
KPI_MAX_ITERATIONS=8
KPI_MAX_TOKENS_PER_CALL=4000
KPI_SCHEMA_CACHE_TTL_SECONDS=3600
```
All are optional except the provider key — DB values override env, env overrides defaults.

---

## 16. Audit & observability

Every interesting action writes a row.

| Table | Captures |
|---|---|
| `kpi_query_run` | Every `execute_safe_query` call. Source, user, company, post-validator SQL, success / error, row count, duration, truncated flag. |
| `kpi_nl_run` | Every NL→SQL agent invocation. Prompt, final SQL, explanation, provider, model, iterations, tokens, duration, full step timeline (JSON). |
| `kpi_chat_message` | Every chat turn (user + assistant). Includes the full assistant pipeline result and agent_steps for replay. |
| `kpi_schema_snapshot` | Every schema refresh. `is_current` marks the live one; old rows kept. |

The frontend "View agent steps" panel in the KPI editor reads `kpi_nl_run.steps` directly — you get an exact replay of what tools the LLM called and what each returned.

---

## 17. Known limits & caveats

1. **Row cap = 50k**. Hardcoded default; injected at SQL level + enforced again post-fetch. Set `truncated=True` on the result if hit.
2. **Wall-clock timeout = 30s**. `SET LOCK_TIMEOUT` is best-effort — doesn't protect against CPU-bound queries.
3. **Schema cache TTL = 1h**. Newly-added columns are invisible until refresh; the agent will hallucinate them only if they appear in the snapshot.
4. **Param whitelist is fixed.** Only `:start_date`, `:end_date`, `:company_id`, `:user_id`. No custom binds; literals required for anything else.
5. **Tenant filter is opt-in.** Bind params are always supplied but auto-injection of `WHERE company_id = :company_id` is Phase I work — today a careless author can cross tenants.
6. **`KpiVersion` is immutable.** Edit = new row + `current_version_id` bump. Tiles reference `kpi_id`, so they always run the latest.
7. **Chart picker is heuristic.** Rule-based, no ML. Pie cap at 6 categories; everything bigger falls back to bar/table.
8. **Raw SQL ↔ Builder is one-way.** A `BuilderSpec` compiles to SQL deterministically; the reverse (raw SQL → spec) isn't supported, so a hand-written KPI stays in raw mode forever.
9. **Chat sessions don't share.** Per-user. No collaboration on a single chat thread in Phase B.
10. **Phase B3 columns exist but are stubs.** `kpi_chat_message.insight` + `recommendations` + `kpi_chat_session.rolling_summary` are migrated but not populated by code yet.
11. **Insight + summarizer failures degrade silently.** When B3 lands, an LLM hiccup on the second pass won't fail the turn — the user just gets no insight strip.
12. **Schema explorer is dual-gated.** `kpi:schema` permission + an in-code `_is_super_admin()` check. Redundant; future cleanup will pick one.

---

## 18. File index

### 18.1 Backend
| Path | Role |
|---|---|
| `backend/kpi_studio/router.py` | Mounts all sub-routers under `/api/v1/kpi`; health check |
| `backend/kpi_studio/config.py` | `KpiStudioConfig` dataclass — auth, engines, LLM provider, excluded tables |
| `backend/kpi_studio/models.py` | All 11 SQLAlchemy models |
| `backend/kpi_studio/schemas.py` | Pydantic request / response models |
| `backend/kpi_studio/deps.py` | FastAPI DI: auth, DB session, config |
| `backend/kpi_studio/api/schema.py` | Schema explorer + relationship CRUD endpoints |
| `backend/kpi_studio/api/kpis.py` | KPI CRUD + preview + run |
| `backend/kpi_studio/api/nl.py` | `/nl/status`, `/nl/generate`, `/nl/suggest-kpis` |
| `backend/kpi_studio/api/chat.py` | Chat sessions + SSE turn endpoint |
| `backend/kpi_studio/api/dashboards.py` | Dashboard CRUD + items + layout + assignments + auto-decorate |
| `backend/kpi_studio/api/settings.py` | Settings get / put |
| `backend/kpi_studio/services/introspector.py` | `reflect_schema`, `persist_snapshot`, `get_current_snapshot`, `build_graph` |
| `backend/kpi_studio/services/schema_context.py` | Renders snapshot to LLM-facing markdown |
| `backend/kpi_studio/services/sql_safety.py` | **`validate_select_query` — the safety guard** |
| `backend/kpi_studio/services/executor.py` | **`execute_safe_query` — validation → run → audit** |
| `backend/kpi_studio/services/chart_picker.py` | `suggest_chart` heuristic |
| `backend/kpi_studio/services/nl2sql.py` | Single-shot NL→SQL (legacy fallback) |
| `backend/kpi_studio/services/nl2sql_tools.py` | The 5 tools + their handlers |
| `backend/kpi_studio/services/nl2sql_agent.py` | **`run_agent` — the agentic loop** |
| `backend/kpi_studio/services/preflight.py` | Planner ↔ Resolver disambiguator |
| `backend/kpi_studio/services/chat_service.py` | Sessions + `run_turn` orchestration |
| `backend/kpi_studio/services/settings_service.py` | Singleton KpiSettings with DB→env→default fallback |
| `backend/kpi_studio/services/spec_compiler.py` | Phase C `BuilderSpec` → SQL + chart_config |
| `backend/kpi_studio/services/kpi_suggester.py` | Phase J LLM-generated KPI proposals for a table |
| `backend/kpi_studio/services/dashboard_decorator.py` | Phase J.2 AI visual polish for tiles |
| `backend/kpi_studio/services/relationship_service.py` | Table-relationship CRUD + auto-seed |
| `backend/kpi_studio/services/chat_summarizer.py` | Phase B3 stub — rolling summary |
| `backend/kpi_studio/services/insight_generator.py` | Phase B3 stub — insights + recommendations |
| `backend/kpi_studio/services/time_periods.py` | `resolve_period(name, start, end)` |
| `backend/kpi_studio/providers/llm/base.py` | `LlmProvider` protocol + dataclasses |
| `backend/kpi_studio/providers/llm/openai_compatible.py` | OpenAI-SDK-based concrete provider (also Cerebras, Ollama Cloud) |
| `backend/kpi_studio/providers/llm/factory.py` | `build_provider_from_env()` |
| `backend/alembic/versions/w7x8y9z0a1b2_*` | Schema snapshot table |
| `backend/alembic/versions/x8y9z0a1b2c3_*` | A1: definition, version, query_run |
| `backend/alembic/versions/y9z0a1b2c3d4_*` | A2: dashboard, dashboard_item |
| `backend/alembic/versions/b1c2d3e4f5g6_*` | Dashboard assignments |
| `backend/alembic/versions/b2c3d4e5f6h7_*` | `kpi_version.time_column` |
| `backend/alembic/versions/c3d4e5f6h7i8_*` | NL run audit log |
| `backend/alembic/versions/d4e5f6h7i8j9_*` | Singleton kpi_settings |
| `backend/alembic/versions/e5f6h7i8j9k0_*` | Seed "KPI Studio" menu |
| `backend/alembic/versions/f6h7i8j9k0l1_*` | Chat tables |
| `backend/alembic/versions/g7h8i9j0k1l2_*` | Smart Analysis menu |
| `backend/alembic/versions/h3i4j5k6l7m8_*` | Chat insight / recommendations columns |
| `backend/alembic/versions/h4i5j6k7l8m9_*` | `kpi_version.builder_spec` |
| `backend/alembic/versions/h5i6j7k8l9m0_*` | Dashboard-item grid coords + visual overrides |
| `backend/alembic/versions/h7i8j9k0l1m2_*` | Table relationships table |
| `backend/alembic/versions/l3m4n5o6p7q8_*` | `kpi_settings.domain_knowledge` |
| `backend/alembic/versions/z0a1b2c3d4e5_*` | Per-company menu seeding (idempotent) |

### 18.2 Frontend
| Path | Role |
|---|---|
| `frontend/src/app/features/kpi-studio/kpi-studio.routes.ts` | Lazy-loaded routes |
| `frontend/src/app/features/kpi-studio/models/schema.types.ts` | TS interfaces |
| `frontend/src/app/features/kpi-studio/services/kpi.service.ts` | KPI CRUD + preview / run |
| `frontend/src/app/features/kpi-studio/services/nl.service.ts` | `generate()`, `suggestKpis()` |
| `frontend/src/app/features/kpi-studio/services/dashboard.service.ts` | Dashboards + items + layout + assignments |
| `frontend/src/app/features/kpi-studio/services/chat.service.ts` | Sessions + SSE turn Observable |
| `frontend/src/app/features/kpi-studio/services/kpi-schema.service.ts` | Schema + relationships |
| `frontend/src/app/features/kpi-studio/services/settings.service.ts` | Settings singleton |
| `frontend/src/app/features/kpi-studio/pages/kpi-list/` | KPI library |
| `frontend/src/app/features/kpi-studio/pages/kpi-editor/` | Authoring (SQL + builder + NL) |
| `frontend/src/app/features/kpi-studio/pages/dashboards-list/` | Dashboard library |
| `frontend/src/app/features/kpi-studio/pages/dashboard-view/` | Render + edit mode |
| `frontend/src/app/features/kpi-studio/pages/schema-explorer/` | SuperAdmin schema UI |
| `frontend/src/app/features/kpi-studio/pages/settings/` | SuperAdmin LLM config |
| `frontend/src/app/features/kpi-studio/pages/chat/` | Smart-analysis chat |
| `frontend/src/app/features/kpi-studio/components/chart-renderer/` | Type → visual |
| `frontend/src/app/features/kpi-studio/components/chart-style-picker/` | Type + config picker |
| `frontend/src/app/features/kpi-studio/components/kpi-builder-pane/` | Phase C wells |
| `frontend/src/app/features/kpi-studio/components/kpi-card/` | Dashboard tile |
| `frontend/src/app/features/kpi-studio/components/chat-panel/` | Reusable message list + input |
| `frontend/src/app/features/kpi-studio/components/period-selector/` | Date range picker |
| `frontend/src/app/features/kpi-studio/components/generate-prompt-dialog/` | NL→SQL prompt dialog |
| `frontend/src/app/features/kpi-studio/components/suggest-kpis-dialog/` | Phase J picker |
| `frontend/src/app/features/kpi-studio/components/animated-number/` | Animated scorecard |

---

## 19. Eval harness (T-001, shipped 2026-05-23)

> Roadmap-tracked addendum. Subsequent shipped roadmap items (T-002, T-003, …) will land as §19.x sub-sections; large enough ones graduate to their own top-level section once the roadmap stabilises. Glossary moved to §20.


The eval harness fires golden cases through the *full* production pipeline (preflight → agent → safety → execute) and records pass/fail per case. CI uses the pass-rate delta as a regression signal — no prompt or pipeline change is safe to merge without it.

The framework is **seed-empty by design**: the team owns defining what "golden" means for SRMB-specific KPIs. Authoring is manual today; auto-promotion from high-rated chat turns lands with T-401.

### 19.1 Why it exists

Every later improvement in the roadmap (T-101 determinism, T-201 self-healing, T-301 glossary, T-401 exemplars, T-601 entity resolver, T-701 schema-drift, T-901 OpenRouter, T-902 stage routing) changes either prompts, models, retrieved context, or the safety pipeline. Without an eval harness, "is this change a regression?" becomes a guess. With it, CI gives a hard answer in seconds.

### 19.2 Data model

Three tables, all owned by `kpi_studio` ([backend/kpi_studio/models.py](backend/kpi_studio/models.py)):

| Table | Purpose | Cascade |
|---|---|---|
| `kpi_eval_case` | Golden case spec — prompt + expectations | — |
| `kpi_eval_run` | One runner invocation; aggregates + knowledge versions | — |
| `kpi_eval_case_result` | Per-case outcome inside a run | DELETE CASCADE both parents |

**Case expectations** (all optional — missing fields skip the comparator, never count as fail):
- `expected_tables` — list of table names that must appear in the produced SQL.
- `strict_tables` — if true, produced SQL touching tables *outside* `expected_tables` also fails.
- `expected_columns` — qualified names like `customer.name`; matched permissively (`c.name` alias also matches if bare name lines up).
- `expected_row_count_min` / `expected_row_count_max` — inclusive range the result row count must land within.
- `golden_sql` — canonical SQL a human would write; not compared verbatim (SQL has many valid spellings), rendered as a diff hint in reports when the case fails.
- `pinned_snapshot_id` — pin a case to a specific schema snapshot; cases run against the wrong snapshot are marked `skipped`.
- `tags` — free-form labels for filtering (`critical`, `adversarial`, `regression-2026-Q2`).

**Failure codes** (stable, machine-readable, stored as a JSON list on `KpiEvalCaseResult.failure_reasons`):
`tables_missing`, `tables_extra`, `columns_missing`, `row_count_low`, `row_count_high`, `sql_exec_failed`, `agent_no_proposal`, `agent_timeout`, `provider_error`.

**Run knowledge fingerprint** — every `KpiEvalRun` stamps `snapshot_id`, `prompt_version`, `glossary_version`, `exemplar_set_hash`. T-002 populates `prompt_version` from env; T-301 + T-401 populate the others. This is how a degraded pass rate is correlated against a config change.

### 19.3 Runner

[backend/kpi_studio/eval/runner.py](backend/kpi_studio/eval/runner.py) — `run_eval(*, db, config, tags=None, case_ids=None, triggered_by="cli", against_snapshot_id=None, on_case=None) → EvalSummary`.

Pipeline per case (matches the production code path exactly — it calls the same `nl2sql_agent.run_agent` and `execute_safe_query` the chat endpoint uses):

1. Load the case.
2. Pinned-snapshot check → `skipped` if mismatched.
3. `run_agent(...)` with effective `KpiSettings` caps. Exceptions → `error` + `provider_error`.
4. If the agent didn't propose SQL → `fail` + `agent_no_proposal`.
5. `execute_safe_query(...)` on the produced SQL. Safety / executor failures → record `sql_exec_failed`.
6. Parse `tables_referenced` + `columns_referenced` from the SQL via `sqlglot`.
7. Run the four comparators; record reason codes for anything that trips.
8. `pass` iff `failure_reasons` is empty.

`on_case` callback streams outcomes as they complete (the CLI uses this for live progress lines).

### 19.4 CLI

[backend/kpi_studio/eval/cli.py](backend/kpi_studio/eval/cli.py) — `python -m kpi_studio.eval [subcommand]`.

```
python -m kpi_studio.eval run
python -m kpi_studio.eval run --tags critical
python -m kpi_studio.eval run --tags critical regression
python -m kpi_studio.eval run --case 12 --case 17
python -m kpi_studio.eval run --against-snapshot 42
python -m kpi_studio.eval run --json              # machine-readable summary
python -m kpi_studio.eval list-cases [--include-inactive]
```

**Exit codes**:
- `0` — every case passed, or no cases matched (unless `--require-cases` was set).
- `1` — at least one case failed or errored.
- `2` — invalid invocation, or no LLM provider configured (unless `--allow-no-provider`).

CI hook example (block merges that drop pass rate by >5% — implementation lives in your CI YAML, the CLI just provides the exit code + JSON):

```bash
python -m kpi_studio.eval run --json > eval.json || exit 1
```

### 19.5 API

All gated to `kpi:settings` (SuperAdmin only) — cases contain hand-crafted SQL and the runner spends LLM tokens; neither should be exposed to regular users.

[backend/kpi_studio/api/eval.py](backend/kpi_studio/api/eval.py):

| Method | Path | Notes |
|---|---|---|
| GET | `/eval/cases` | List active cases. `?include_inactive=true&tag=critical` |
| POST | `/eval/cases` | Create case (`EvalCaseCreate` body) |
| GET | `/eval/cases/{id}` | One case |
| PUT | `/eval/cases/{id}` | Partial update (Pydantic `exclude_unset`) — set `is_active=false` to soft-delete |
| DELETE | `/eval/cases/{id}` | Hard delete (rare; prefer soft) |
| GET | `/eval/runs` | Recent runs newest-first, `?limit=50` |
| GET | `/eval/runs/{id}` | One run with embedded `results: [EvalCaseResultPayload]` |
| POST | `/eval/runs` | Fire a run synchronously (`EvalRunRequest` body); blocks until done. Async via T-003 scheduler when it lands. |

### 19.6 Migration

[backend/alembic/versions/j7k8l9m0n1o2_create_kpi_eval_tables.py](backend/alembic/versions/j7k8l9m0n1o2_create_kpi_eval_tables.py) — chains off `i6j7k8l9m0n1` (the FWS perm-flags / merge migration that collapsed the prior dual-head chain). Idempotent (probes `INFORMATION_SCHEMA.TABLES` before each `create_table`). Downgrade drops in reverse cascade order. *(History note: originally authored as `i6j7k8l9m0n1` chained off `h5i6j7k8l9m0`; both clashed with the parallel chain and were renumbered.)*

### 19.7 Runner pipeline (matches production chat exactly)

The runner calls the same three services in the same order that `chat_service.run_turn` does — so a passing case proves the *user-facing* path works, not just the agent in isolation:

1. **Pre-flight Planner** ([preflight.py](backend/kpi_studio/services/preflight.py)) — only when `KpiSettings.preflight_enabled`. `ask_user` verdicts terminate the case as `fail` (reason: `agent_no_proposal`, with the clarification question stashed on `failure_detail`); `abort` verdicts become `error` (reason: `agent_timeout`). `ready` verdicts feed `verdict.intent` into the agent as the prompt while the original `case.prompt` rides along as `original_prompt`.
2. **NL→SQL Agent** ([nl2sql_agent.run_agent](backend/kpi_studio/services/nl2sql_agent.py)) — same caps as production (from `KpiSettings`). Token usage is *accumulated* across preflight + agent calls.
3. **Executor** ([executor.execute_safe_query](backend/kpi_studio/services/executor.py)) — same safety layer (`sql_safety.validate_select_query`), same audit (`kpi_query_run`).

### 19.8 Frontend (`/kpi-studio/eval`)

[frontend/src/app/features/kpi-studio/pages/eval/](frontend/src/app/features/kpi-studio/pages/eval/) — three files:

- [eval-page.component.ts](frontend/src/app/features/kpi-studio/pages/eval/eval-page.component.ts) — admin shell with two tabs:
  - **Runs** tab: list newest-first; pass-rate banded green/yellow/red (≥90 / ≥60 / lower); click a row to expand per-case results inline with status pills + reason tags + tooltip on `failure_detail`.
  - **Cases** tab: search by name/tag, activate/deactivate toggle, per-row "Run only this case" action, "New case" button opens the create-or-edit dialog.
- [eval-case-dialog.component.ts](frontend/src/app/features/kpi-studio/pages/eval/eval-case-dialog.component.ts) — single dialog for create + edit; tags / expected_tables / expected_columns are entered as comma-separated values.
- [services/eval.service.ts](frontend/src/app/features/kpi-studio/services/eval.service.ts) — typed HTTP wrapper over `/kpi/eval/*`.

Header has a single **Run now** button that POSTs `/eval/runs`, auto-switches to the Runs tab when the response arrives, and pre-expands the new run so results are visible without an extra click.

Route registered as [`/kpi-studio/eval`](frontend/src/app/features/kpi-studio/kpi-studio.routes.ts) (lazy-loaded standalone component). SuperAdmin-only — the backend gate (`kpi:settings`) already enforces this, and the sidebar entry is hidden for everyone else via the standard `has-permission` directive.

### 19.9 What ships next on this thread

Phase 0 remaining:
- ~~**T-002** prompt-version stamping~~ — **shipped, see §19.10**.
- ~~**T-003** APScheduler infra~~ — **shipped, see §19.11**.
- **T-004** provider health-check — catches T-901/T-902 misconfigurations at save time, not query time.

CI hook (eval pass-rate regression block) was deferred — the CLI exposes the right exit codes (0/1/2) and `--json --require-cases` flags, so wiring it into whichever CI system the team standardises on is a ~2h job whenever that decision lands.

### 19.10 Prompt-version stamping (T-002, shipped 2026-05-23)

Every NL audit row now carries the knowledge fingerprint of the run that produced it. When a pass rate drifts after a deploy, the four stamps tell you *which* knowledge layer to look at first.

**Stamped fields** (all nullable so pre-T-002 rows survive):
- **`prompt_version`** — semver string from env `KPI_PROMPT_VERSION`. Default `"0.0.0"`. Bump MAJOR for breaking system-prompt rewrites, MINOR for behavioural tweaks, PATCH for wording fixes. Currently stamped on `KpiNlRun`, `KpiChatMessage`, and `KpiEvalRun` (latter wired in T-001).
- **`glossary_version`** — placeholder, `None` until T-301 ships the structured glossary; then becomes a monotonic counter that bumps on every term mutation.
- **`schema_snapshot_id`** — FK → `kpi_schema_snapshot`. Always populated when a snapshot exists. Resolved once per audit row via `services.knowledge_versions.current()` (cheap — single indexed SELECT).
- **`exemplar_set_hash`** — placeholder, `None` until T-401 ships the exemplar bank; then a sha256 of the contributing exemplars' `(id, updated_at)` tuples.

**Where the stamping happens**:
- [backend/kpi_studio/services/knowledge_versions.py](backend/kpi_studio/services/knowledge_versions.py) — single resolver. `current(db) → KnowledgeFingerprint`. Spread into model constructors via `**fp.as_kwargs()`.
- [api/nl.py](backend/kpi_studio/api/nl.py) — every `/nl/generate` audit row.
- [services/chat_service.py](backend/kpi_studio/services/chat_service.py) — three insert sites (assistant turn, failure turn, clarify turn). User turns leave the columns NULL.

**Migration**: [alembic/versions/k8l9m0n1o2p3_add_prompt_versioning.py](backend/alembic/versions/k8l9m0n1o2p3_add_prompt_versioning.py). Idempotent column-add against both tables + FK to `kpi_schema_snapshot` + indices on `prompt_version` for filterable history queries.

**How to bump**: drop `KPI_PROMPT_VERSION=1.0.0` (or whatever) into the environment, redeploy. Every row written after that carries the new stamp. Older rows keep the old stamp — no rewriting.

### 19.11 Scheduler infrastructure (T-003, shipped 2026-05-23)

In-process APScheduler with a register-by-name registry + audit-wrapped execution. Unblocks every later task that needs background work (T-204 anchor refresh, T-601 value indexer, T-701 schema-drift detection, T-703 incremental indexer, T-707 data-shape drift).

**Why in-process**: per project design, KPI Studio adds no external broker (no Celery, no Redis). Scales to multi-worker by running the scheduler in only one worker — the `KPI_SCHEDULER_ENABLED` env gate handles this.

**Files**:
- [backend/kpi_studio/services/scheduler.py](backend/kpi_studio/services/scheduler.py) — registry + `BackgroundScheduler` + audit wrapper. Public surface: `register()`, `start_scheduler()`, `shutdown_scheduler()`, `list_jobs()`, `run_now()`, `list_recent_runs()`.
- [backend/kpi_studio/services/scheduled_jobs.py](backend/kpi_studio/services/scheduled_jobs.py) — central registration module. Auto-imports on startup. Currently registers one job (`scheduler_heartbeat`, every 6 minutes) as a liveness probe; future tasks add their jobs here.
- [backend/kpi_studio/api/jobs.py](backend/kpi_studio/api/jobs.py) — three admin endpoints (`GET /jobs`, `GET /jobs/{name}/runs`, `POST /jobs/{name}/trigger`).
- [backend/app/main.py](backend/app/main.py) — startup/shutdown event hooks call `start_scheduler()` / `shutdown_scheduler()`.

**Migration**: [alembic/versions/l9m0n1o2p3q4_create_scheduled_job_run.py](backend/alembic/versions/l9m0n1o2p3q4_create_scheduled_job_run.py) — creates `kpi_scheduled_job_run` (one row per execution: `job_name`, `trigger_source`, `status` ∈ {running, success, failed, cancelled}, `error`, `items_processed`, `duration_ms`, `detail_json`).

**How to add a job** (this is the contract every Phase 1+ task will use):
```python
# In kpi_studio/services/scheduled_jobs.py
from kpi_studio.services import scheduler

def my_drift_check(db: Session) -> int:
    # ... do work ...
    return rows_processed  # surfaced as items_processed on the audit row

scheduler.register(
    name="schema_drift_check",
    func=my_drift_check,
    interval_seconds=900,  # or cron="0 2 * * *"
    description="Polls INFORMATION_SCHEMA + diffs against current snapshot.",
)
```
Job functions may accept zero or one positional arg; the wrapper passes a fresh `Session` when the signature accepts one. Return value (when an int) is recorded as `items_processed` — useful for trending.

**Per-job kill switch**: `KPI_JOB_<UPPER_NAME>_ENABLED=false` env var disables one job without a code change. Useful for noisy / heavy jobs in dev.

**Admin UI**: [frontend/src/app/features/kpi-studio/pages/jobs/](frontend/src/app/features/kpi-studio/pages/jobs/) — list of registered jobs, trigger summary, last-run status, "Run now" button, expandable per-run history. Auto-refreshes every 30s. Route: [`/kpi-studio/jobs`](frontend/src/app/features/kpi-studio/kpi-studio.routes.ts).

**Failure handling**: every job is wrapped — exceptions are caught, the row is flipped to `status='failed'` with the truncated error, and APScheduler is *not* told the job failed (keeps the schedule alive). A worker crash mid-job leaves the row stuck at `running` — surface those (status filter + `started_at < now - margin`) for "missed heartbeat" diagnostics later.

---

### 19.12 OpenRouter + per-stage routing + provider healthcheck (T-901 + T-902 + T-004, shipped 2026-05-23)

Three roadmap items shipped together because they share the settings page. Net effect: one provider + one API key + a model-string per pipeline stage + an automated probe surface that catches misconfigs before users hit them.

**Stage taxonomy** ([backend/kpi_studio/stages.py](backend/kpi_studio/stages.py)) — six declared stages, snake_case keys + plain-English labels + descriptions + a `built` flag:

| Key | Label | Built? |
|---|---|---|
| `preflight_planner` | Pre-flight planner | ✅ |
| `agent_default` | Agent (NL → SQL) | ✅ |
| `insight_generator` | Insight generator | ✅ |
| `chart_picker` | Chart picker (LLM-augmented) | future |
| `sanity_check` | Result sanity check | future (T-204) |
| `intent_classifier` | Intent classifier | future (T-206) |

Future tasks add their stage by appending to `STAGES` in [stages.py](backend/kpi_studio/stages.py) — one source of truth, no UI changes needed.

**T-901 — OpenRouter as a first-class provider**

Added `openrouter` to the [factory](backend/kpi_studio/providers/llm/factory.py) and [settings_service defaults](backend/kpi_studio/services/settings_service.py). Same OpenAI-compatible protocol; default base URL `https://openrouter.ai/api/v1`, default model `anthropic/claude-3.5-sonnet`. Optional `HTTP-Referer` + `X-Title` extras (recommended by OpenRouter for routing fairness + analytics) plumbed through [openai_compatible.py](backend/kpi_studio/providers/llm/openai_compatible.py)'s new `extra_headers` constructor arg.

**T-902 — Per-stage model routing**

`KpiSettings` gains:
- `stage_models JSON` — `{stage_key: model_string}` map.
- `default_stage_model String(200)` — fallback when a stage is unset.

Resolution order in [settings_service.provider_for_stage()](backend/kpi_studio/services/settings_service.py):
1. `stage_models[stage_key]`
2. `default_stage_model`
3. `openai_model` (the legacy single-model field)
4. provider factory default

The returned provider shares the same key + base_url + extras as the default; only the model differs. That's the design intent: one provider, many models — built around OpenRouter's "one key, ~200 models" pattern.

Wired call-sites:
- [chat_service.run_turn](backend/kpi_studio/services/chat_service.py) — preflight uses `STAGE_PREFLIGHT_PLANNER`, agent uses `STAGE_AGENT_DEFAULT`, insight uses `STAGE_INSIGHT_GENERATOR`.
- [api/nl.py /nl/generate](backend/kpi_studio/api/nl.py) — both `mode=agent` and `mode=single` route through `STAGE_AGENT_DEFAULT`.

**T-004 — Provider healthcheck**

[backend/kpi_studio/services/provider_healthcheck.py](backend/kpi_studio/services/provider_healthcheck.py) — walks every stage, collapses duplicate `(provider, model)` pairs, fires one 1-token `complete()` per unique pair. Result cached in-process for 5 minutes so repeat page loads don't pay the round-trip cost.

Three triggers:
- **Save-time**: `PUT /settings` runs the probe; refuses the save with HTTP 400 + `{code: "healthcheck_failed", failures: [...]}` unless the body carries `force: true`. UI shows a "Save anyway" button to bypass.
- **On-demand**: `POST /settings/healthcheck` with optional `force` re-probes. The settings page auto-calls it on load (cached) and on save.
- **Scheduled**: [services/scheduled_jobs.py](backend/kpi_studio/services/scheduled_jobs.py) registers `provider_healthcheck` to run weekly via T-003. Findings surface in the admin jobs page.

**API**

| Method | Path | Notes |
|---|---|---|
| GET | `/settings` | Echoes `stages` taxonomy + `effective_stage_models` (resolved values) + the 4 new T-901/T-902 fields. |
| PUT | `/settings` | Accepts `openrouter_referer / openrouter_app_name / stage_models / default_stage_model / force`. Runs healthcheck post-save; rolls back on failure unless `force=true`. |
| POST | `/settings/healthcheck` | `{force?: bool}`; returns per-probe results with `stages: [keys...]` so the UI can colour each row in the matrix. |

**Frontend** ([pages/settings/](frontend/src/app/features/kpi-studio/pages/settings/))

The settings page gains:
- **Provider dropdown** with OpenRouter as a 4th option.
- **OpenRouter extras** sub-section (visible only when provider == openrouter): App URL + App name inputs that become `HTTP-Referer` + `X-Title` headers.
- **Per-stage routing matrix**: one row per declared stage. Each row shows label + description + model input (placeholder = effective fallback) + healthcheck pill (green/red with latency or error tooltip). "Default stage model" row at the bottom.
- **Run health check button** in the matrix header — triggers a fresh probe.
- **Save anyway button** beside Save — sends `force: true` to bypass a failed healthcheck.

Future stages render greyed-out with a "future" pill so admins know the column exists but does nothing yet — keeps the matrix self-documenting as the roadmap evolves.

**Migration**: [m0n1o2p3q4r5_add_openrouter_and_stage_routing.py](backend/alembic/versions/m0n1o2p3q4r5_add_openrouter_and_stage_routing.py) — applied. Four new nullable columns on `kpi_settings`; idempotent.

---

### 19.13 Multi-provider refactor + tabbed Settings page (shipped 2026-05-25)

The single-provider model from T-901/T-902 didn't scale to the "different models from different providers for different tasks" use case admins were asking for. This refactor splits provider configuration from stage routing entirely: any number of providers can coexist, each stage independently picks both **which provider** and **which model** to use.

**Data model**

- New table [kpi_llm_provider_config](backend/kpi_studio/models.py) — one row per configured provider. Columns: `provider_config_id`, `kind` (one of `openai / openrouter / cerebras / ollama_cloud / azure_openai`), `display_name`, `api_key`, `base_url`, `openrouter_referer`, `openrouter_app_name`, `is_active`, `description`, audit.
- `KpiSettings.stage_models` JSON now stores either:
  - **New shape**: `{stage_key: {provider_config_id: int, model: str}}`.
  - **Legacy shape**: `{stage_key: "model-string"}` — still readable for backward compat; falls through to the legacy single-provider columns on KpiSettings.
- Migration [n1o2p3q4r5s6_create_provider_configs.py](backend/alembic/versions/n1o2p3q4r5s6_create_provider_configs.py) auto-creates one provider config from the existing single-provider row (display_name = "Migrated (openai)"). Admins rename via the UI.

**Backend services**

- [provider_config_service.py](backend/kpi_studio/services/provider_config_service.py) — CRUD + `build_provider(row, model=...)` that instantiates a provider with the row's key + base_url + OpenRouter extras.
- [settings_service.provider_for_stage(eff, stage_key, db=)](backend/kpi_studio/services/settings_service.py) rewritten: looks up `provider_config_id` via the service when the new shape is present; falls back to the legacy single-provider path when it isn't. `resolve_stage_provider_config_id()` + `resolve_stage_model()` are the new accessors.
- [provider_healthcheck.run_healthcheck](backend/kpi_studio/services/provider_healthcheck.py) enumerates every stage + every active unrouted provider. Groups duplicates so two stages on the same `(config_id, model)` probe once. A new `probe_provider_config(db, id, model=)` powers the per-card Test button without touching the cache.

**API**

| Method | Path | Notes |
|---|---|---|
| GET | `/settings/providers` | list every provider config (active + inactive) + allowed kinds |
| POST | `/settings/providers` | create — invalidates healthcheck cache |
| GET | `/settings/providers/{id}` | one config |
| PUT | `/settings/providers/{id}` | update; `KEEP_API_KEY` sentinel preserves stored key |
| DELETE | `/settings/providers/{id}` | hard delete; **409 if still routed by any stage** |
| POST | `/settings/providers/{id}/test` | real round-trip; returns `model_used` + `response_model` + `latency_ms` + `response_preview` so the admin can see exactly which upstream service handled the call |

`/settings/healthcheck` continues to work — now walks the provider configs + stage routes instead of the single global provider.

**Frontend — tabbed settings page**

[pages/settings/settings.component.ts](frontend/src/app/features/kpi-studio/pages/settings/settings.component.ts) was rebuilt as a `<mat-tab-group>` with five tabs:

1. **Providers** — card grid of all configured providers + "Add provider" button. Each card has:
   - Display name + kind pill + active/inactive indicator.
   - API key status, base URL, default model.
   - OpenRouter-only extras shown when kind is OpenRouter.
   - **Per-card Test button** that opens a diagnostic dialog showing `model requested`, `model echoed back by upstream`, `base URL`, `latency`, `response preview`, plus a mismatch warning when the echoed model differs from what was requested. This is the answer to "is this hitting OpenAI or OpenRouter?" — the upstream model echo is definitive.
   - Edit / Activate-Deactivate / Delete actions.

2. **Stage routing** — per-stage rows with **two dropdowns**: Provider (select from active configs, default = fallback) and Model (free-text with the effective model as placeholder). Plus a "default stage model" row at the bottom for stages left blank. Health pills per row come from the latest probe.

3. **Agent caps** — token budget, max iterations, max tokens per call (unchanged).

4. **Domain knowledge** — the existing markdown textarea (unchanged).

5. **Health** — full probe-result table: status pill, provider label, model, latency, comma-separated stage keys that resolve to this pair, error text. Plus a summary banner.

Supporting dialogs:
- [provider-dialog.component.ts](frontend/src/app/features/kpi-studio/pages/settings/provider-dialog.component.ts) — create/edit a provider config. Picking a kind auto-fills the kind's default base URL + shows a hint with the expected model-string format.
- [provider-test-dialog.component.ts](frontend/src/app/features/kpi-studio/pages/settings/provider-test-dialog.component.ts) — full diagnostic result. Echo-mismatch warning explains when OpenRouter's upstream routing is normal vs. when it's suspicious.

**Why the OpenRouter test confusion is gone now**

Old design: one global `/settings/test` endpoint. If a save was rolled back (T-004 healthcheck refusing the new config), the test still hit the old provider — admin couldn't tell which key/model was actually in play.

New design: each provider card has its own Test button hitting that card's specific config. The result dialog shows:
- The base URL actually called.
- The model name sent.
- The model name the upstream echoed back.
- A latency reading.
- The first 80 chars of the response text.

If the admin's "Production OpenRouter" card returns `latency=420ms · response_model=anthropic/claude-3.5-sonnet`, they know with certainty their key + URL + model are routing through OpenRouter. If it returns `response_model=gpt-4o`, they're hitting OpenAI directly — the diagnostic banner flags the mismatch.

### 19.14 LLM call-log observability (shipped 2026-05-25)

After the 19.13 multi-provider rollout the admin had no way to see what the agent actually sent the LLM on a given chat turn. A failure in a chat reply could be a bad prompt, a bad SQL plan, an upstream 429, or a malformed response — without the raw HTTP body you're guessing. This section adds **per-call HTTP recording** with correlation grouping so the full LLM trace of one user-facing operation is one click away.

**Data model**

- New table [kpi_llm_call_log](backend/kpi_studio/models.py): one row per outbound LLM HTTP request. Columns: `call_log_id`, `correlation_id` (UUID4 string — same value across every call that belongs to one user op), `trigger_source` (`chat / nl_generate / eval / healthcheck_auto / healthcheck_manual / provider_test / settings_test / unknown`), `trigger_ref_kind` + `trigger_ref_id` (e.g. `kpi_chat_message` + the message id), `user_id`, `provider_config_id`, `provider_kind`, `provider_label`, `base_url`, `model`, `stage_key`, `request_method`, `request_path`, `request_body`, `request_headers` (masked), `request_truncated`, `response_status`, `response_body`, `response_truncated`, `succeeded`, `error`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `started_at`, `finished_at`. Indexed on `started_at`, `correlation_id`, `(provider_config_id, started_at)`, `(trigger_source, started_at)`.
- Two new columns on `kpi_settings`: `call_logging_enabled` (BIT, default `True`) and `call_log_retention_days` (INT, default `7`).
- Migration [p3q4r5s6t7u8_create_llm_call_log.py](backend/alembic/versions/p3q4r5s6t7u8_create_llm_call_log.py) creates the table + indices + settings columns. Idempotent.

**Recording pipeline**

[services/call_logger.py](backend/kpi_studio/services/call_logger.py) owns three concerns:

1. **Correlation scope**: `log_context(trigger_source, user_id=, trigger_ref_kind=, trigger_ref_id=)` is a context manager that opens a UUID4 correlation and stores it in a `contextvars.ContextVar`. Every nested LLM call reads that var and writes the same id, so one chat turn (~12 calls across preflight → agent → insight) shows up as one group.
2. **Per-stage scope**: `stage_scope(stage_key)` is a nested scope that tags subsequent calls with which pipeline stage they served (used by the UI to colour by stage).
3. **Row insert**: `record(...)` is called from inside `OpenAICompatibleProvider._post` for every request — success, 4xx, 5xx, timeout, JSON-parse error all logged. Headers are masked (`Authorization`, `X-Api-Key`, etc → `***`); bodies are capped at 64KB per side with a `truncated` flag.

`prune_older_than(db, days)` powers the daily scheduled cleanup.

**Where correlation IDs are opened** (the "user-facing entry points"):

| Entry point | File | trigger_source |
|---|---|---|
| Chat turn | [services/chat_service.py](backend/kpi_studio/services/chat_service.py) `run_turn` | `chat` |
| NL → SQL endpoint | [api/nl.py](backend/kpi_studio/api/nl.py) | `nl_generate` |
| Provider "Test connection" | [api/providers.py](backend/kpi_studio/api/providers.py) | `provider_test` |
| Settings test (global) | [api/settings.py](backend/kpi_studio/api/settings.py) POST `/test` | `settings_test` |
| Healthcheck (auto) | scheduled `provider_healthcheck` job | `healthcheck_auto` |
| Healthcheck (manual) | POST `/settings/healthcheck` | `healthcheck_manual` |
| Eval runs | (T-001 runner) | `eval` |

ThreadPoolExecutor probes in `provider_healthcheck` re-establish the contextvar inside each worker (contextvars don't propagate across threads by default) so all probes from one healthcheck batch share a correlation.

**API**

| Method | Path | Notes |
|---|---|---|
| GET | `/settings/call-logs` | cursor-paginated list. Query params: `limit` (1..500, default 50), `cursor` (last `call_log_id` from prior page), `trigger_source`, `provider_config_id`, `ok` (true/false), `correlation_id`. Returns summary rows (no bodies — keeps the response cheap). |
| GET | `/settings/call-logs/{id}` | full detail including pretty-print-ready request + response bodies. |
| GET | `/settings/call-logs/correlation/{correlation_id}` | every call sharing a correlation id, chronological. |
| DELETE | `/settings/call-logs` | hard-delete every row. The admin "clean slate" affordance. |

All SuperAdmin-only (`kpi:settings` permission).

**Cost / disk gates**

- `call_logging_enabled` toggle in the Call log tab — when OFF, `call_logger.record` short-circuits and no rows are written. Manual healthcheck probes still log so a "fix it now" diagnostic isn't lost.
- `call_log_retention_days` — daily `call_log_prune` job (registered in [scheduled_jobs.py](backend/kpi_studio/services/scheduled_jobs.py)) hard-deletes rows older than the cutoff. Default 7 days. Cheap query — delete by indexed `started_at` range.

**Frontend — Call log tab**

A sixth tab on the Settings page:

- **Toolbar card**: persist-toggle + retention input + save button. Saves via `PUT /settings` with `force=true` so an unrelated unhealthy stage doesn't block a logging-only change.
- **Filters row**: source dropdown (matches `CALL_LOG_SOURCES`), provider dropdown (active configs), status (all/success/failure), correlation id text field with Enter-to-apply.
- **Table**: timestamp, source pill, provider + model, stage pill, status pill, latency, tokens (`total (prompt/completion)`). Per-row actions: a "Show siblings" tree-icon (opens correlation view) and an "Open detail" affordance.
- **Cursor pagination**: "Load older" appends the next page; `next_cursor=null` disables the button.
- **Purge all**: confirmation-guarded; calls `DELETE /settings/call-logs`.

Detail dialog ([call-log-detail-dialog.component.ts](frontend/src/app/features/kpi-studio/pages/settings/call-log-detail-dialog.component.ts)) has two modes:

- **Single-call**: meta panel (provider, model, base URL, trigger, started, http status + latency, token breakdown, correlation id with "Show siblings" button) + tabbed JSON viewer (Request body / Request headers / Response body) with `pretty(JSON)` formatting and a "Copy JSON" action.
- **Correlation siblings**: accordion of every call that shared the id, auto-expanded on the first failure. Each accordion has `<details>` sections for request body / headers / response body. Lets the admin walk one chat turn end-to-end.

**How to read it for a chat-turn debug**

1. Open Chat, ask the question that misbehaved. Note the time.
2. Open Settings → Call log. The most recent rows are the agent's calls.
3. Click "Show siblings" on any row from that chat turn — the dialog opens with every preflight + agent + insight call grouped.
4. The first failure is auto-expanded. Read the request body to see what prompt the agent sent, the response body to see what came back. The headers tab shows the (masked) auth + provider-specific routing headers.

**Files**

- Migration: [alembic/versions/p3q4r5s6t7u8_create_llm_call_log.py](backend/alembic/versions/p3q4r5s6t7u8_create_llm_call_log.py)
- Model: [kpi_studio/models.py](backend/kpi_studio/models.py) (`KpiLlmCallLog`, `CALL_LOG_SOURCES`)
- Service: [kpi_studio/services/call_logger.py](backend/kpi_studio/services/call_logger.py)
- Provider patch: [kpi_studio/providers/llm/openai_compatible.py](backend/kpi_studio/providers/llm/openai_compatible.py) (`_post` records on every request)
- API: [kpi_studio/api/call_logs.py](backend/kpi_studio/api/call_logs.py)
- Frontend service: [services/call-logs.service.ts](frontend/src/app/features/kpi-studio/services/call-logs.service.ts)
- Frontend tab: [pages/settings/call-log-tab.component.ts](frontend/src/app/features/kpi-studio/pages/settings/call-log-tab.component.ts)
- Frontend detail dialog: [pages/settings/call-log-detail-dialog.component.ts](frontend/src/app/features/kpi-studio/pages/settings/call-log-detail-dialog.component.ts)

---

## 20. Glossary

| Term | Meaning |
|---|---|
| **SQL Agent** | The tool-using LLM loop in `nl2sql_agent.py` that turns prompts into SELECT SQL. |
| **Pre-flight Planner** | The disambiguation pass in `preflight.py` that runs before the SQL Agent. |
| **Snapshot** | A row in `kpi_schema_snapshot` — a frozen reflection of the target DB used to feed the LLM and the schema explorer UI. |
| **KPI Version** | An immutable `kpi_version` row. Every save creates a new one; `kpi_definition.current_version_id` points at the active one. |
| **Builder Spec** | Phase C JSON describing wells (axis / values / filters) → compiled to SQL by `spec_compiler.py`. |
| **Domain Knowledge Hub** | Free-form text in `kpi_settings.domain_knowledge` fed to the LLM as application context. |
| **Tile** | A `kpi_dashboard_item` — one KPI rendered on a dashboard with position + visual overrides. |
| **Decoration** | Phase J.2 LLM-proposed per-tile visual polish (icon, animation, filter) applied via `dashboard_decorator`. |
| **Insight / Recommendation** | Phase B3 second-pass LLM output saved to `kpi_chat_message.insight` / `recommendations`. Not generated yet. |
