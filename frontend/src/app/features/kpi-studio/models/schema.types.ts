// Mirrors kpi_studio/schemas.py — keep in sync if backend types change.

export interface ColumnInfo {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
  default: string | null;
  autoincrement: boolean;
  comment: string | null;
}

export interface ForeignKeyInfo {
  constrained_columns: string[];
  referred_schema: string | null;
  referred_table: string;
  referred_columns: string[];
  name: string | null;
}

export interface IndexInfo {
  name: string;
  columns: string[];
  unique: boolean;
}

export interface TableInfo {
  schema: string | null;
  name: string;
  comment: string | null;
  columns: ColumnInfo[];
  primary_key: string[];
  foreign_keys: ForeignKeyInfo[];
  indexes: IndexInfo[];
  row_count_estimate: number | null;
}

export interface SchemaSnapshotMeta {
  snapshot_id: number;
  database_key: string;
  table_count: number;
  relationship_count: number;
  created_at: string;
  created_by: number | null;
  is_current: boolean;
}

export interface SchemaListResponse {
  snapshot: SchemaSnapshotMeta;
  tables: TableInfo[];
}

// ---------------------------------------------------------------------------
// Phase F — Table relationships (data modeling)
// ---------------------------------------------------------------------------

export type RelationshipCardinality = 'many_to_one' | 'one_to_one' | 'one_to_many';
export type RelationshipSource = 'auto' | 'manual';

export interface TableRelationship {
  relationship_id: number;
  company_id: number | null;
  from_schema: string | null;
  from_table: string;
  from_column: string;
  to_schema: string | null;
  to_table: string;
  to_column: string;
  cardinality: RelationshipCardinality;
  source: RelationshipSource;
  is_active: boolean;
}

export interface TableRelationshipCreate {
  from_schema?: string | null;
  from_table: string;
  from_column: string;
  to_schema?: string | null;
  to_table: string;
  to_column: string;
  cardinality?: RelationshipCardinality;
}

export interface TableRelationshipListResponse {
  items: TableRelationship[];
  total: number;
}

export interface TableRelationshipAutoSeedResponse {
  inserted: number;
  skipped: number;
  total_active: number;
}

export interface SchemaRefreshResponse {
  snapshot: SchemaSnapshotMeta;
  refreshed: boolean;
}

export interface GraphNode {
  id: string;
  label: string;
  schema: string | null;
  column_count: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  columns: string[];
  name: string | null;
}

export interface SchemaGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ---------------------------------------------------------------------------
// Phase A1 — KPI authoring + execution
// ---------------------------------------------------------------------------

export type ChartType =
  | 'scorecard'
  | 'stat_group'
  | 'bar'
  | 'line'
  | 'pie'
  | 'table';

export interface ChartConfig {
  type: ChartType;
  config: Record<string, any>;
  /** Phase A6 — visual style (theme + animations). Stored as a JSON
   * blob so we can extend without backend schema changes. */
  style?: ChartStyle;
}

// ---------------------------------------------------------------------------
// Phase A6 — Chart styling
// ---------------------------------------------------------------------------

export type ChartTheme = 'default' | 'dark' | 'vibrant' | 'minimal';

export interface ChartStyle {
  theme?: ChartTheme;
  /** When true, charts run a short enter animation on mount. */
  animations?: boolean;
}

export const CHART_THEMES: { value: ChartTheme; label: string; preview: string }[] = [
  { value: 'default', label: 'Default',  preview: '#4a90e2' },
  { value: 'dark',    label: 'Dark',     preview: '#1a1d23' },
  { value: 'vibrant', label: 'Vibrant',  preview: '#ff6b6b' },
  { value: 'minimal', label: 'Minimal',  preview: '#888888' },
];

/** Per-theme color palette used by bar / pie / line. The first colour is
 * the "primary" used for single-series charts; later colours fill stacked
 * categories. */
export const CHART_PALETTES: Record<ChartTheme, string[]> = {
  default: ['#4a90e2', '#50c878', '#ff9f43', '#ee5a52', '#a55eea', '#26d0ce', '#fd79a8', '#fdcb6e'],
  dark:    ['#4dd0e1', '#81c784', '#ffb74d', '#e57373', '#ba68c8', '#4fc3f7', '#f06292', '#ffd54f'],
  vibrant: ['#ff6b6b', '#feca57', '#48dbfb', '#1dd1a1', '#5f27cd', '#ee5253', '#ff9ff3', '#54a0ff'],
  minimal: ['#444444', '#777777', '#aaaaaa', '#cccccc', '#888888', '#666666', '#999999', '#bbbbbb'],
};

export interface ChartSuggestion {
  type: ChartType;
  config: Record<string, any>;
  reason: string;
  alternates: ChartType[];
}

export interface ExecutionResult {
  columns: string[];
  rows: any[][];
  row_count: number;
  truncated: boolean;
  duration_ms: number;
  rewritten_sql: string;
  notes: string[];
  suggestion: ChartSuggestion | null;
}

export interface KpiVersionSummary {
  version_id: number;
  version_no: number;
  chart_type: ChartType;
  created_at: string;
  created_by: number | null;
}

export interface KpiSummary {
  kpi_id: number;
  name: string;
  description: string | null;
  chart_type: ChartType;
  current_version_id: number | null;
  owner_user_id: number | null;
  company_id: number | null;
  is_active: boolean;
  updated_at: string;
}

export interface KpiDetail {
  kpi_id: number;
  name: string;
  description: string | null;
  company_id: number | null;
  owner_user_id: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  current_version_id: number | null;
  query_text: string | null;
  chart_config: ChartConfig | null;
  database_key: string;
  time_column: string | null;
  builder_spec?: BuilderSpec | null;
  versions: KpiVersionSummary[];
}

export interface KpiListResponse {
  items: KpiSummary[];
  total: number;
}

// ---------------------------------------------------------------------------
// Smart Builder — Power BI–style "drag fields into wells" authoring (Phase C)
// ---------------------------------------------------------------------------

export type BuilderAggregation =
  | 'SUM' | 'AVG' | 'COUNT' | 'COUNT_DISTINCT' | 'MIN' | 'MAX';

export type BuilderFormat = 'number' | 'currency' | 'percent' | 'short' | 'date' | 'text';

export type BuilderSortDir = 'asc' | 'desc';

export type BuilderFilterOp =
  | '=' | '!=' | '>' | '>=' | '<' | '<='
  | 'in' | 'not_in'
  | 'like' | 'not_like'
  | 'is_null' | 'is_not_null'
  | 'between';

export type BuilderChartType =
  | 'scorecard' | 'stat_group' | 'bar' | 'pie' | 'line' | 'table';

export interface BuilderSource {
  kind?: 'table';
  schema?: string | null;
  name: string;
}

export interface BuilderField {
  column: string;
  /** Phase F — table the column lives on. Omitted = source table.
   * When set, the spec compiler walks the relationship graph and
   * auto-emits the LEFT JOIN. */
  table?: string | null;
  schema?: string | null;
  agg?: BuilderAggregation | null;
  format?: BuilderFormat | null;
  sort?: BuilderSortDir | null;
  alias?: string | null;
}

export interface BuilderFilter {
  column: string;
  op: BuilderFilterOp;
  value?: any;
}

/** Phase G — calculated column. ``expression`` is a free-form T-SQL
 * snippet that evaluates against the source table; the spec compiler
 * wraps the source in a CTE so any well or filter can reference the
 * alias just like a real column. */
export interface DerivedColumn {
  alias: string;
  expression: string;
  description?: string | null;
  format?: BuilderFormat | null;
}

/** Phase G.2 — predicate on an *aggregated* value, emitted as a
 * ``HAVING`` clause. Distinct from BuilderFilter (WHERE) because it
 * runs after GROUP BY: filter on SUM(amount) > 1000, COUNT(*) >= 5,
 * etc. Same operator vocabulary as BuilderFilter. */
export interface AggregateFilter {
  column: string;
  agg: BuilderAggregation;
  op: BuilderFilterOp;
  value?: any;
}

export interface BuilderSpec {
  chart_type: BuilderChartType;
  source: BuilderSource;
  wells: Record<string, BuilderField[]>;
  filters?: BuilderFilter[];
  top_n?: number | null;
  time_column?: string | null;
  /** Phase G — calculated columns that wrap the source in a CTE.
   * Aliases become referenceable like real columns in any well. */
  derived_columns?: DerivedColumn[];
  /** Phase G.2 — HAVING predicates on aggregated values. */
  aggregate_filters?: AggregateFilter[];
}

export interface KpiCreateRequest {
  name: string;
  description?: string | null;
  query_text?: string | null;
  chart_config?: ChartConfig | null;
  database_key?: string;
  time_column?: string | null;
  builder_spec?: BuilderSpec | null;
}

export interface KpiUpdateRequest {
  name?: string;
  description?: string | null;
  query_text?: string;
  chart_config?: ChartConfig;
  database_key?: string;
  time_column?: string | null;
  builder_spec?: BuilderSpec | null;
}

export interface KpiPreviewRequest {
  query_text?: string | null;
  builder_spec?: BuilderSpec | null;
  database_key?: string;
  /** Phase A5 — time period filter. */
  period?: TimePeriod | null;
  start_date?: string | null;
  end_date?: string | null;
}

export interface KpiRunRequest {
  period?: TimePeriod | null;
  start_date?: string | null;
  end_date?: string | null;
  /** Phase J.2 — dashboard cards send per-card filters here so the
   * same KPI can show a different slice on each board it appears on. */
  extra_filters?: BuilderFilter[];
}

// ---------------------------------------------------------------------------
// Phase A5 — Time periods
// ---------------------------------------------------------------------------

export type TimePeriod =
  | 'daily'
  | 'weekly'
  | 'monthly'
  | 'quarterly'
  | 'yearly'
  | 'last_5_years'
  | 'custom';

export const TIME_PERIODS: { value: TimePeriod; label: string }[] = [
  { value: 'daily',         label: 'Daily (24h)' },
  { value: 'weekly',        label: 'Weekly' },
  { value: 'monthly',       label: 'Monthly' },
  { value: 'quarterly',     label: 'Quarterly' },
  { value: 'yearly',        label: 'Yearly' },
  { value: 'last_5_years',  label: 'Last 5 years' },
  { value: 'custom',        label: 'Custom range' },
];

export interface TimePeriodSelection {
  period: TimePeriod | null;
  /** ISO 8601 strings; only used when period === 'custom'. */
  start_date?: string | null;
  end_date?: string | null;
}

// ---------------------------------------------------------------------------
// Phase A2 — Dashboards
// ---------------------------------------------------------------------------

export type DashboardScope = 'user' | 'company';
export type CardSize = 'sm' | 'md' | 'lg' | 'wide';

export const CARD_SIZES: CardSize[] = ['sm', 'md', 'lg', 'wide'];
export const CARD_SIZE_LABELS: Record<CardSize, string> = {
  sm: 'Small (1×)',
  md: 'Medium (2×)',
  lg: 'Large (3×)',
  wide: 'Wide (4×)',
};
/** Number of grid columns each card spans. */
export const CARD_SIZE_SPAN: Record<CardSize, number> = {
  sm: 1, md: 2, lg: 3, wide: 4,
};

export type CardAnimation = 'fade' | 'slide' | 'scale' | 'none';
export const CARD_ANIMATIONS: CardAnimation[] = ['fade', 'slide', 'scale', 'none'];

export interface DashboardItem {
  item_id: number;
  kpi_id: number;
  kpi_name: string;
  kpi_chart_type: ChartType;
  /** Full saved chart_config (type + per-chart config + style). Cards
   * render with this so the author's choice survives — falling back to
   * the executor's auto-suggestion silently overrode it before. */
  kpi_chart_config?: ChartConfig | null;
  kpi_is_active: boolean;
  position: number;
  size_class: CardSize;
  /** Phase D — Power BI–style grid coordinates (12-column grid).
   * Always populated by the API; the CSS Grid layout reads/writes these
   * directly. ``grid_h`` is in row units (default row height = 80px). */
  grid_x: number;
  grid_y: number;
  grid_w: number;
  grid_h: number;
  title_override: string | null;
  /** Phase J.2 — per-card visual + filter overrides set by AI Polish.
   * NULL / empty means "use the KPI's default". */
  icon?: string | null;
  animation_in?: CardAnimation | null;
  animation_out?: CardAnimation | null;
  /** Bar / line axis title overrides. Ignored for other chart types. */
  x_label?: string | null;
  y_label?: string | null;
  /** Extra WHERE filters merged with the KPI's spec at execute time. */
  extra_filters?: BuilderFilter[];
}

export interface DashboardSummary {
  dashboard_id: number;
  name: string;
  description: string | null;
  scope: DashboardScope;
  owner_user_id: number | null;
  company_id: number | null;
  is_active: boolean;
  item_count: number;
  updated_at: string;
}

export interface DashboardDetail {
  dashboard_id: number;
  name: string;
  description: string | null;
  scope: DashboardScope;
  owner_user_id: number | null;
  company_id: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  items: DashboardItem[];
}

export interface DashboardListResponse {
  items: DashboardSummary[];
  total: number;
}

export interface DashboardCreateRequest {
  name: string;
  description?: string | null;
  scope?: DashboardScope;
}

export interface DashboardUpdateRequest {
  name?: string;
  description?: string | null;
  scope?: DashboardScope;
}

export interface DashboardItemCreateRequest {
  kpi_id: number;
  size_class?: CardSize;
  title_override?: string | null;
}

export interface DashboardItemUpdateRequest {
  size_class?: CardSize;
  title_override?: string | null;
  icon?: string | null;
  animation_in?: CardAnimation | null;
  animation_out?: CardAnimation | null;
  x_label?: string | null;
  y_label?: string | null;
  extra_filters?: BuilderFilter[] | null;
}

export interface DashboardLayoutEntry {
  item_id: number;
  position: number;
  size_class?: CardSize;
  /** Phase D — gridster sends explicit coords on every drop / resize. */
  grid_x?: number;
  grid_y?: number;
  grid_w?: number;
  grid_h?: number;
  /** Phase J.2 — AI Polish bundles style + filter changes into the same
   * layout PUT so the user's "Save" applies everything in one trip. */
  title_override?: string | null;
  icon?: string | null;
  animation_in?: CardAnimation | null;
  animation_out?: CardAnimation | null;
  x_label?: string | null;
  y_label?: string | null;
  extra_filters?: BuilderFilter[] | null;
}

export interface DashboardLayoutRequest {
  items: DashboardLayoutEntry[];
}

// ---------------------------------------------------------------------------
// Phase A3 — NL → SQL
// ---------------------------------------------------------------------------

export interface NlStatus {
  enabled: boolean;
  provider: string | null;
}

export interface NlValidation {
  ok: boolean;
  message: string | null;
  findings: string[];
  rewritten_sql: string | null;
}

export interface NlGenerateRequest {
  prompt: string;
  /** ``agent`` (default) runs the multi-step tool-use loop; ``single``
   * one-shots the prompt with the full schema as context. */
  mode?: 'agent' | 'single';
}

export interface NlAgentStep {
  /** Step kinds:
   *   tool_call / tool_error / thought / final / abort  - SQL agent
   *   planner_question / resolver_answer                - Pre-flight loop
   * Both sources stream through the same SSE channel; the chat panel
   * renders them with different icons but the same timeline UI. */
  type:
    | 'tool_call' | 'tool_error' | 'thought' | 'final' | 'abort'
    | 'planner_question' | 'resolver_answer';
  tool?: string | null;
  args?: Record<string, any> | null;
  output?: any;
  error?: string | null;
  latency_ms?: number | null;
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export type LlmProviderName = 'openai' | 'cerebras' | 'ollama_cloud';

/** Sentinel matching backend ``KEEP_API_KEY`` — sent as openai_api_key
 * when the user hasn't touched the field, so the backend leaves the
 * stored value alone. Any other string (including "") is a write. */
export const KEEP_API_KEY = '__KEEP__';

export interface KpiSettings {
  // Stored values (null when fall-through to env).
  llm_provider: string | null;
  has_api_key: boolean;
  openai_model: string | null;
  openai_base_url: string | null;
  token_budget: number | null;
  max_iterations: number | null;
  max_tokens_per_call: number | null;
  /** System Knowledge Hub — admin-curated business context appended to
   *  the chatbot agent's system prompt on every turn. */
  domain_knowledge: string | null;
  // Effective values (DB → env → default) — what the agent actually uses.
  effective_provider: string | null;
  effective_model: string | null;
  effective_token_budget: number;
  effective_max_iterations: number;
  effective_max_tokens_per_call: number;
  effective_has_key: boolean;
  using_env_fallback: boolean;
}

export interface KpiSettingsUpdate {
  llm_provider?: string | null;
  /** Use ``KEEP_API_KEY`` to leave the stored value alone; "" clears it;
   * any other string is a new value. */
  openai_api_key?: string;
  openai_model?: string | null;
  openai_base_url?: string | null;
  token_budget?: number | null;
  max_iterations?: number | null;
  max_tokens_per_call?: number | null;
  /** ``null``/omitted = leave alone; ``""`` = clear; anything else = save. */
  domain_knowledge?: string | null;
}

export interface SettingsTestResult {
  ok: boolean;
  message: string;
  provider?: string | null;
  model?: string | null;
  latency_ms?: number | null;
}

// ---------------------------------------------------------------------------
// Phase B1 — Smart-analysis chatbot
// ---------------------------------------------------------------------------

export type ChatRole = 'user' | 'assistant';

/** Discriminator for the *kind* of assistant turn:
 *   'answer'  - canonical successful query turn (default for all
 *               existing/legacy data and the happy path).
 *   'clarify' - Pre-flight Planner asking the user a follow-up
 *               question. ``content`` holds the question; no
 *               sql/chart/insight; ``recommendations`` carries the
 *               suggested-options chips for one-tap replies.
 * Future variants ('reject', 'plan', etc.) reuse the same column. */
export type ChatMessageKind = 'answer' | 'clarify';

export interface ChatMessage {
  chat_message_id: number;
  chat_session_id: number;
  role: ChatRole;
  kind?: ChatMessageKind;
  content: string;
  // Assistant-only fields:
  sql?: string | null;
  rewritten_sql?: string | null;
  result_columns?: string[] | null;
  result_rows?: any[][] | null;
  chart_config?: ChartConfig | null;
  agent_steps?: NlAgentStep[] | null;
  // Phase B3 — second LLM pass narrative + actionable follow-ups.
  insight?: string | null;
  recommendations?: string[] | null;
  succeeded: boolean;
  error?: string | null;
  provider?: string | null;
  model?: string | null;
  tokens: number;
  duration_ms: number;
  created_at: string;
}

export interface ChatSessionSummary {
  chat_session_id: number;
  title: string | null;
  is_active: boolean;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatSessionDetail {
  chat_session_id: number;
  title: string | null;
  company_id: number | null;
  user_id: number | null;
  is_active: boolean;
  rolling_summary: string | null;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

export interface ChatSessionListResponse {
  items: ChatSessionSummary[];
  total: number;
}

export interface ChatTurnResponse {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
}

// ---------------------------------------------------------------------------
// Phase J — AI suggests KPIs for a table
// ---------------------------------------------------------------------------

export interface KpiSuggestRequest {
  table: string;
  schema?: string | null;
  count?: number;
}

export interface KpiSuggestionItem {
  name: string;
  description: string;
  builder_spec: BuilderSpec;
  chart_config: ChartConfig;
  sql: string;
}

export interface KpiSuggestResponse {
  items: KpiSuggestionItem[];
  tokens: number;
  latency_ms: number;
  model: string;
  error?: string | null;
}

// ---------------------------------------------------------------------------
// Phase J.2 — AI auto-decorate (layout proposal for a dashboard)
// ---------------------------------------------------------------------------

export interface DashboardDecorationItem {
  item_id: number;
  grid_x: number;
  grid_y: number;
  grid_w: number;
  grid_h: number;
  size_class: string;
  title_override?: string | null;
  icon?: string | null;
  animation_in?: CardAnimation | null;
  animation_out?: CardAnimation | null;
  x_label?: string | null;
  y_label?: string | null;
  extra_filters?: BuilderFilter[];
}

export interface DashboardDecorateResponse {
  items: DashboardDecorationItem[];
  tokens: number;
  latency_ms: number;
  model: string;
  error?: string | null;
  used_fallback: boolean;
}

export interface NlGenerateResponse {
  sql: string;
  explanation: string;
  provider: string;
  model: string;
  latency_ms: number;
  usage: Record<string, any>;
  validation: NlValidation;
  /** Phase A7 — describes how the answer was reached. ``single`` mode
   * returns an empty ``steps`` array. */
  mode: 'agent' | 'single';
  steps: NlAgentStep[];
  iterations: number;
  total_tokens: number;
  succeeded: boolean;
  error?: string | null;
}

// ---------------------------------------------------------------------------
// Phase A4 — Dashboard assignments (role + user grants)
// ---------------------------------------------------------------------------

export interface DashboardAssignment {
  assignment_id: number;
  dashboard_id: number;
  role_id: number | null;
  user_id: number | null;
  granted_by: number | null;
  granted_at: string;
}

export interface DashboardAssignmentCreate {
  /** Exactly one of role_id / user_id must be set. */
  role_id?: number;
  user_id?: number;
}
