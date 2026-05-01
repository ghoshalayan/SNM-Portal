# KPI Studio — Setup

Operational guide for the KPI Studio module. Pairs with [KPI-STUDIO-PLAN.md](KPI-STUDIO-PLAN.md) (which covers architecture and phasing).

---

## Environment variables

Add these to `backend/.env`. Everything is optional — the module degrades gracefully when keys are absent.

### Database

```env
# Phase 1 onwards.
# Connection string the KPI executor uses to run user-authored SQL.
# Defaults to DB_CONNECTION_STRING when blank.
# Strongly recommended: point this at a SQL Server login with SELECT-only
# permissions on the tables/views you want to expose to KPIs.
KPI_DSN=
```

### Permissions

KPI Studio enforces three permission codes via the host's RBAC layer:

| Code | Who should have it | What it gates |
|---|---|---|
| `kpi:view` | All KPI users | Read dashboards + cards + chat history |
| `kpi:author` | Authors / analysts | Create/edit/delete cards, run preview SQL, use chatbot |
| `kpi:admin` | Admins | Manage shared dashboards, manage chat-history retention, see audit log |

The diagnostic schema-explorer endpoints (`/api/v1/kpi/schema/*`) require **SuperAdmin** — they are gated independently of the codes above.

### LLM provider (Phase A3 onwards)

```env
# Which provider the NL→SQL pipeline talks to. One of:
#   openai | azure_openai | ms_foundry | gemini | cerebras | ollama_cloud
# Leave blank to disable LLM features (manual SQL still works).
KPI_LLM_PROVIDER=openai

# ---- OpenAI (wire this first) ------------------------------------------
# Cheapest path to working NL→SQL. Cerebras and Ollama Cloud reuse the
# same OpenAI-compatible impl with different base_url + key.
KPI_OPENAI_API_KEY=
KPI_OPENAI_MODEL=gpt-4o
KPI_OPENAI_BASE_URL=https://api.openai.com/v1

# ---- Azure OpenAI (production/enterprise option) -----------------------
KPI_AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
KPI_AZURE_OPENAI_API_KEY=
KPI_AZURE_OPENAI_DEPLOYMENT=gpt-4o
KPI_AZURE_OPENAI_API_VERSION=2024-10-21

# ---- Microsoft Foundry (azure-ai-inference SDK) ------------------------
KPI_MS_FOUNDRY_ENDPOINT=
KPI_MS_FOUNDRY_API_KEY=
KPI_MS_FOUNDRY_MODEL=

# ---- Google Gemini -----------------------------------------------------
KPI_GEMINI_API_KEY=
KPI_GEMINI_MODEL=gemini-2.0-flash

# ---- Cerebras (OpenAI-compatible) --------------------------------------
KPI_CEREBRAS_API_KEY=
KPI_CEREBRAS_MODEL=llama-3.3-70b
KPI_CEREBRAS_BASE_URL=https://api.cerebras.ai/v1

# ---- Ollama Cloud (OpenAI-compatible) ----------------------------------
KPI_OLLAMA_CLOUD_API_KEY=
KPI_OLLAMA_CLOUD_MODEL=llama3.3
KPI_OLLAMA_CLOUD_BASE_URL=https://ollama.com/v1
```

### Executor limits (sane defaults — override only if needed)

```env
KPI_STATEMENT_TIMEOUT_SECONDS=30
KPI_ROW_CAP=50000
KPI_RESULT_BYTE_CAP=10485760            # 10 MB
KPI_CHAT_HISTORY_COMPACT_AFTER_PAIRS=3  # rolling-summary compaction trigger
```

---

## Recommended DB role (when ready)

Even with safety checks at the parser/executor level, a defence-in-depth read-only login is the cheapest insurance. Provision once, point `KPI_DSN` at it, never worry about a missed validator rule again.

```sql
-- Run as DBA / sysadmin
USE master;
CREATE LOGIN snm_kpi_reader WITH PASSWORD = '<strong-random>';

USE SNMPortal;
CREATE USER snm_kpi_reader FOR LOGIN snm_kpi_reader;

-- Read everything in dbo (or limit to a curated view set).
ALTER ROLE db_datareader ADD MEMBER snm_kpi_reader;

-- Belt-and-braces: deny anything that could mutate or escalate.
DENY INSERT, UPDATE, DELETE, EXECUTE, ALTER, CONTROL ON SCHEMA::dbo TO snm_kpi_reader;
DENY VIEW DATABASE STATE TO snm_kpi_reader;
DENY VIEW SERVER STATE TO snm_kpi_reader;
```

DSN format:
```
mssql+pyodbc://snm_kpi_reader:<password>@<host>:1433/SNMPortal?driver=ODBC+Driver+17+for+SQL+Server
```

You can ship A1 + A2 with `KPI_DSN` blank (it falls back to the main connection); switch to the dedicated login before A3 ships, since user-authored / LLM-generated SQL is the larger attack surface.

---

## Migrations

KPI Studio piggybacks on the host's Alembic chain (single migration history is operationally simpler than two). Tables are prefixed `kpi_*`.

| Phase | Migration | Effect |
|---|---|---|
| 1 ✅ | `w7x8y9z0a1b2_create_kpi_schema_snapshot` | Adds `kpi_schema_snapshot` |
| A1 ✅ | `x8y9z0a1b2c3_create_kpi_a1_tables` | Adds `kpi_definition`, `kpi_version`, `kpi_query_run` |
| A2 ✅ | `y9z0a1b2c3d4_create_kpi_a2_dashboards` | Adds `kpi_dashboard`, `kpi_dashboard_item` |
| A2.1 ✅ | `z0a1b2c3d4e5_add_kpi_studio_menus` | Seeds **KPI Studio** sidebar menu + grants **SuperAdmin** full access |
| B1 (planned) | `_create_kpi_chat` | Adds `kpi_chat_session`, `kpi_chat_message` |

Run with the existing tooling — no separate Alembic env:

```bash
cd backend
alembic upgrade head
```

> **If you see "Failed to load KPIs" or "Failed to load Dashboards" in the
> UI, the most common cause is forgetting this step.** The backend tries
> to query `kpi_*` tables that don't exist yet, the API returns 500, and
> the frontend banner now surfaces the SQL error directly so you can
> confirm.

After the migration runs, log in as a SuperAdmin user and you'll see
**KPI Studio** in the sidebar with three submenus: Dashboards, KPIs,
Schema Explorer.

---

## Chat history retention

Chat sessions and messages are retained **forever** by default — you asked for this. Operationally:

- Original messages always stored to `kpi_chat_message` (audit + "show full history" UX).
- After every 3 Q&A pairs (configurable via `KPI_CHAT_HISTORY_COMPACT_AFTER_PAIRS`), the LLM context window is rebuilt as `[system prompt] + [rolling summary] + [last 3 pairs]`.
- The rolling summary is regenerated by a small LLM call after each compaction trigger and stored on `kpi_chat_session.rolling_summary`.
- Storage is cheap; this only affects the prompt sent to the model, not what users see in the chat panel.

If you ever want to hard-cap retention, add a daily job that deletes messages older than N days **plus** regenerates the rolling summary so context isn't lost.

---

## Provider switch checklist

Switching `KPI_LLM_PROVIDER` requires:

1. Set the new provider's API key + endpoint env vars.
2. Restart the FastAPI process (env vars read at startup).
3. Smoke-test by opening the chatbot and asking a known-good question.
4. Watch `kpi_query_run` for a few executions — if generated SQL changes shape (e.g. different join style), tweak the system prompt in `providers/llm/<provider>.py` rather than the validator.

The `LlmProvider` interface is intentionally narrow — `complete(messages, tools=None)` — so swapping backends doesn't ripple into application code.

---

## Useful runtime knobs

| Knob | Where | Effect |
|---|---|---|
| `KPI_DSN` empty | env | Reuse the main app DB connection |
| `KPI_LLM_PROVIDER` empty | env | Hide chatbot UI; manual KPI authoring still works |
| `KPI_STATEMENT_TIMEOUT_SECONDS` | env | Per-query timeout — lower if your DB is shared with the OLTP workload |
| `KPI_ROW_CAP` | env | Hard ceiling on returned rows |
| `kpi_definition.is_active = 0` | DB | Soft-delete a card; dashboards hide it but history is preserved |
| `kpi_dashboard.scope` | DB | Flip a dashboard from `user` → `company` to share it |

---

## Phase-1 diagnostic page

The schema-explorer page at `/kpi-studio/schema` is available to **SuperAdmin only**. It is *not* the user-facing surface — it's a debugging tool you'll occasionally want when an LLM-generated query references the wrong table. From A2 onwards the default `/kpi-studio` lands on the dashboards list, and most users never see the schema explorer.
