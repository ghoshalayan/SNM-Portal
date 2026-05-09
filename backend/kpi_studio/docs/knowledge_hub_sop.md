# SNM Portal — System Knowledge Hub Content

This file is the source-of-truth content for the **System Knowledge Hub**
that backs the AI assistant (Preflight Resolver + NL→SQL Agent).

**How to use:** copy everything between the `=== BEGIN KNOWLEDGE HUB ===`
and `=== END KNOWLEDGE HUB ===` markers below, then paste into
**KPI Studio → Settings → System Knowledge Hub**, and click Save.

The Resolver splits this on blank lines, so each block is one paragraph
that gets indexed and searched independently. Each paragraph leads with
the concept name and packs likely synonyms inline so substring +
token-overlap matching reliably surfaces it.

---

=== BEGIN KNOWLEDGE HUB ===

PORTAL OVERVIEW. SNM Portal is a multi-tenant B2B sales-and-marketing system for SRMB. The pipeline runs Customer → Customer Enquiry → Quotation → Costing → Annexure → Purchase Order. Every business table is tenant-scoped by `companyId` (FK to Company), is soft-deleted via `isActive=1/0`, and carries audit columns (`createdby`, `createdon`, `lastupdateby`, `lastupdateon`) from `AuditMixin` in `app/models/base.py`. The hierarchy is encoded by `UserRoleMap.reportTo`. SuperAdmin and CompanyAdmin bypass parts of the access pipeline; everyone else is filtered by company, hierarchy, and location.

CRITICAL TERMINOLOGY: PREPARED BY. "Prepared by", "created by", "author", "who entered", "who typed", "who keyed in" all refer to the user who originally entered the record. The exact column is `createdby` (integer FK to UserMaster, on every business table via AuditMixin). It NEVER changes after the record is saved — even after handover. Use `WHERE createdby = :user_id` only when the user explicitly asks for "data-entry user", "original author", "who keyed it in", or audit-trail style questions. DO NOT use `createdby` for "my quotations", "my enquiries", "my pipeline", or "team performance" — those mean ownership, not authorship.

CRITICAL TERMINOLOGY: CREATED UNDER / OWNER. "Created under", "owner", "owned by", "owns", "assigned to", "attributed to", "responsible for", "on behalf of", "under user X" all refer to the user the record is hierarchically attributed to. The exact column is `ownerUserId` (integer FK to UserMaster) on `QuotSummary`, `CustomerEnquiry`, and other ownable entities. The `ownerUserId` CAN change via the Handover action. Use `WHERE ownerUserId = :user_id` for "my quotations", "my enquiries", "my pipeline", "team performance", "sales rep dashboards", "what is John handling", and approval routing. The owner's role at creation time is captured in `ownerRoleId` (FK to RoleMaster) and drives number generation (`numGenMode`).

DEFAULT FOR "MY RECORDS" QUESTIONS. When a user says "show me my quotations", "my enquiries", "what I'm working on", "my pipeline", "list mine", "things assigned to me", or "what's in my name", the answer is `WHERE ownerUserId = :user_id` — NOT `createdby`. The same applies to "John's quotations", "Asha's enquiries" — use ownership. Only when the user explicitly says "originally created by", "first authored by", "data entry user", "audit log of who entered", "who keyed in" should you use `createdby`. If the user is ambiguous, default to `ownerUserId` and note the assumption in the explanation.

HANDOVER (OWNERSHIP TRANSFER). A quotation or enquiry can change owner via the Handover endpoint: `POST /api/v1/quotations/{id}/handover` or `POST /api/v1/enquiries/{id}/handover`. Synonyms: handover, transfer ownership, reassign, change owner, hand over to, give to, move to. Effects: `ownerUserId` and `ownerRoleId` are updated. The initiator must hold the `CanTransferOwnership` permission flag, and the target user must be in the initiator's `visible_user_ids` set. Quotation-only side effect: a status of `Approved` auto-reverts to `Draft` so the new owner re-approves. The `createdby` column is unaffected by handover — that is why "prepared by" and "owner" can differ on the same record.

HIERARCHICAL VISIBILITY (FILTER F5). A non-admin user sees a record only if its `ownerUserId` is in their `visible_user_ids` — the set computed by walking `UserRoleMap.reportTo` downwards according to the role's `downwardLevels` flag (`-1` = unlimited). Synonyms: my team, my subordinates, my reportees, my hierarchy, my org, who reports to me, downwards. The role can also include peers (`peerAccess`) and ancestors (`upwardLevels`). SuperAdmin (`IsSuperAdmin=true`) sees all rows. CompanyAdmin (`IsCompanyAdmin=true`) sees all rows within the same company. NOTE: hierarchy filtering uses `ownerUserId`, NEVER `createdby`.

MULTI-TENANCY. Every business table carries `companyId` (FK to Company). Every query MUST include `WHERE companyId = :company_id` — omitting this leaks data across tenants. The current user's company is always available as bind param `:company_id` (the executor auto-binds it). The current user's id is `:user_id`. Synonyms: company, tenant, organization, our company, my company. The only legitimate exception is queries on the Company table itself, run by SuperAdmin.

SOFT DELETE. Every business and master table uses soft delete: a DELETE flips `isActive` to 0, never removes the row. Default to `WHERE isActive = 1` on every query. Honor "show deleted", "include archived", "include inactive" as the user's explicit opt-out — only then drop the filter. Synonyms: deleted, removed, archived, active, inactive, live, current. Tables affected: Customer, CustomerSite, CustomerContact, CustomerEnquiry, QuotSummary, RoleMaster, UserMaster, MenuMaster, every master data table.

QUOTATION LIFECYCLE. The `QuotSummary` table holds quotations. Status flows through (column `status`): Draft → Submitted → Approved → Matured (winning sales path), or Draft → Submitted → Rejected → back to Draft on next edit. A revision creates a new row with `Revised` set on the older row. Approved quotations are read-only except via Revise. Approver actions require the `CanApprove` permission. The Annexure module attaches to Approved quotations. Synonyms: quotation, quote, offer, proposal, RFQ response, draft, submit, approve, reject, mature, revise.

QUOTATION VERSIONING. Quotation revisions chain via `parentQuotId` and `versionNo`. The original row has `parentQuotId = NULL` and `versionNo = 1`. Each Revise inserts a new row with the same parent reference and `versionNo + 1`. To select the latest version of a quotation chain: `SELECT TOP 1 * FROM QuotSummary WHERE (quotId = :id OR parentQuotId = :id) AND isActive = 1 ORDER BY versionNo DESC`. Older versions are read-only — never UPDATE a row whose `versionNo` is not the maximum for its chain. Synonyms: revision, revise, version, latest, current, superseded.

ENQUIRY LIFECYCLE. The `CustomerEnquiry` table holds sales leads. An enquiry feeds zero or one quotation chain. The status column drives the pipeline view (statuses come from a status master and vary per company; common values include New, In-Progress, Won, Lost, Dropped). Each enquiry has line-items in `CustomerEnquiryDetail`, optional costing in `CustomerEnquiryCosting`, and communication logs. Synonyms: enquiry, inquiry, lead, RFQ, opportunity, prospect, sales lead.

COSTING VERSIONING. The `CustomerEnquiryCosting` table holds costing for an enquiry; revisions bump `versionNo` against the same enquiry. Latest costing = highest `versionNo` for that `enquiryId`. Costing does not have a parent-id chain — only the version number. Synonyms: costing, cost sheet, cost analysis, viability.

USER MASTER & ROLE MASTER. `UserMaster` holds user accounts. `RoleMaster` holds role templates. The link `UserRoleMap` records which role a user holds in which company, and which user they report to (`reportTo`). One user can belong to multiple companies with different roles. Each role has flags (IsSuperAdmin, IsCompanyAdmin, downwardLevels, upwardLevels, peerAccess, locationScopeRequired, enforceChildLocationSubset, numGenMode) that drive the access pipeline. The role-templates SuperAdmin / CompanyAdmin / Director / HOD / KRO are seeded per company; admins customize from there. Synonyms: user, employee, role, designation, hierarchy, reports to, manager, KRO, HOD.

LOCATION SCOPE (FILTER F6). Users can be restricted to certain states or districts via `UserLocationMap`. When the role flag `locationScopeRequired = true`, a user only sees records whose state/district is in their location set. KRO roles use `enforceChildLocationSubset = true`, meaning their location set must be a subset of their reportTo's location set, and changes cascade to subordinates. SuperAdmin and CompanyAdmin bypass this filter. Synonyms: location, region, state, district, territory, area, zone.

DATE COLUMNS — AUDIT vs BUSINESS. Distinguish audit dates from business dates. Audit dates are `createdon` (when the row was inserted) and `lastupdateon` (when it was last edited) — these come from AuditMixin on every table. Business dates are domain-specific: `enquiryDate`, `quotationDate`, `expectedDeliveryDate`, `validTill`, etc. When a user asks "enquiries from last month", default to the business date column (`enquiryDate`) NOT the audit column (`createdon`) — the user means the date the enquiry pertains to, not when the row was inserted. Switch to audit dates only when the user explicitly says "entered last month", "added recently", "since I last logged in", or audit-style phrasing.

NUMBER GENERATION (numGenMode). Quotation and enquiry numbers are generated based on the owner's role flag `numGenMode`: `own_code` uses the owner's own code, `parent_code` uses the parent (reportTo) user's code, `select_code` lets the user pick. The role flag is on `RoleMaster.numGenMode`. The owner determines this — meaning `ownerUserId` and `ownerRoleId`, NOT createdby. Synonyms: number, code, prefix, sequence, quote number, enquiry number, document number.

KPI STUDIO MODULE. KPI Studio (under `/kpi-studio` in the UI, `/api/v1/kpi/...` on the backend) is a separate analytics module that owns its own tables prefixed `kpi_` (KPI definitions, dashboards, schema snapshots, settings). The Knowledge Hub edited at Settings → System Knowledge Hub stores domain knowledge in `KpiSettings.domain_knowledge`. The Preflight Resolver searches this blob via paragraph + token match before every NL→SQL run. Synonyms: KPI, dashboard, analytics, metric, chart, kpi studio, knowledge hub, settings.

WORKFLOW: APPROVAL. Quotations require an approver to move from Submitted → Approved. The approver must hold `CanApprove` on the Quotations menu and must be in a position to see the quotation (passes filters F2/F5/F6). Approval is recorded with timestamp and approver user id. Once Approved, the quotation is locked from edits except via Revise (which spawns a new version). A handed-over Approved quotation auto-reverts to Draft. Synonyms: approve, approval, approver, sanction, sign off, authorize.

WORKFLOW: COMMERCIAL HOD APPROVAL FOR ANNEXURES. Annexures attached to a quotation require sign-off from the Commercial HOD role (granular permission: `CanApprove` on the Annexure menu). The annexure cycle is Draft → Submitted → Approved (Commercial HOD) → Sent. Annexure data is auto-populated from the quotation's viability sheet via `annexure_service.py`. Synonyms: annexure, attachment, schedule, addendum, commercial hod, approval, sign off.

PURCHASE ORDER. The `quot_purchase_order` table records the customer's purchase order against a Matured quotation. Every PO is tied to one quotation. PO status, PO date, PO value, and PO number are stored here. A quotation cannot be marked Matured without an attached PO. Synonyms: PO, purchase order, customer order, work order.

COMMUNICATION LOGS. Every customer interaction (call, email, meeting, visit) is captured in `comm_log` against either a Customer, an Enquiry, or a Quotation. Filter by ownership: a user sees comm logs whose parent record's `ownerUserId` is in their visible set (Filter F4 — parent visibility). Synonyms: comm log, communication, call log, follow up, interaction, email log, meeting note.

GOTCHA: "MINE" IS ALWAYS OWNERSHIP. The single most common confusion: a user saying "my X", "things I am working on", "my pipeline", "what's assigned to me", or "list mine" ALWAYS means ownership in this portal — `WHERE ownerUserId = :user_id`. Even though `createdby` is the user who keyed in the record, "mine" never refers to authorship in this domain unless the user adds explicit qualifiers like "originally created" or "data-entry by". When in doubt, choose `ownerUserId` and explain the assumption in the response.

GOTCHA: COUNT BY OWNER, NOT BY AUTHOR. When asked "quotations per salesperson", "enquiries per user", "team workload", "pipeline by rep", group by `ownerUserId` (joined to UserMaster for the name). Grouping by `createdby` undercounts heavy-hitters whose juniors enter records on their behalf and overcounts data-entry clerks who enter records for everyone. The owner is the meaningful business unit.

GOTCHA: HISTORICAL OWNERSHIP IS NOT TRACKED. The current `ownerUserId` is the only ownership recorded. There is no audit trail of past owners on the row itself — handovers do not snapshot the prior owner into a history table (they may be recorded in `comm_log` or change-log tables when those exist). When a user asks "who used to own this", say the data is not directly available unless a change-log table is configured.

=== END KNOWLEDGE HUB ===

---

## Maintenance notes

* **Search index:** the Preflight `lookup_domain` tool splits on blank lines (`\n\s*\n`), normalises with `re.sub(r"[\s_\-]+", " ", text.lower())`, and ranks paragraphs by the count of query tokens (length > 2 chars) appearing as substrings. Top 3 are returned to the LLM.
* **Char limit:** `KpiSettings.domain_knowledge` is capped at 32,000 chars. Current draft is well under.
* **When to edit:** add a new paragraph any time a real conversation surfaces a confusing concept, a new business term, or a workflow the LLM gets wrong. Lead each paragraph with the term + synonyms; the search is keyword-driven, not semantic.
* **Where it gets injected:** see [`backend/kpi_studio/services/preflight.py`](../services/preflight.py) (`lookup_domain` tool, line 94) and [`backend/kpi_studio/services/chat_service.py`](../services/chat_service.py) (`run_preflight` + `system_prompt_extras` to the agent).
* **Versioning:** keep this file in git as the canonical copy. The DB row is a working copy that an admin can paste over. To diff: copy the DB content out of the textarea, paste into a scratch file, `git diff`.
