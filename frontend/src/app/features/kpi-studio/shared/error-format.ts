/**
 * Format HttpErrorResponse-shaped errors into a useful display string.
 *
 * FastAPI returns various detail shapes:
 *   • `{ detail: "string" }`              — simple errors
 *   • `{ detail: { error, message, ... } }` — our structured 4xx
 *   • Pydantic 422 with `{ detail: [{loc, msg, type}, ...] }`
 *   • Plain HTML on 500s with no detail
 *
 * This helper reaches into all of the above + appends the HTTP status so
 * an ops engineer can tell "tables don't exist" (500) from "permission
 * denied" (403) at a glance.
 *
 * Always console.error()s the original so the full payload is available
 * in DevTools for debugging.
 */
export interface FormattedError {
  /** Single-line message safe for a snackbar. */
  message: string;
  /** Multi-line detail safe for a banner. */
  detail: string;
  /** Numeric HTTP status, or 0 for network errors. */
  status: number;
}

export function formatHttpError(err: any, fallback = 'Request failed'): FormattedError {
  // Always log the raw error so DevTools shows the full payload.
  // eslint-disable-next-line no-console
  console.error('[kpi-studio] HTTP error', err);

  const status: number = typeof err?.status === 'number' ? err.status : 0;
  const detail = err?.error?.detail;

  let message = fallback;

  if (typeof err?.error === 'string' && err.error.trim()) {
    // Plain-text response body (rare but happens on some proxies).
    message = err.error.trim();
  } else if (typeof detail === 'string' && detail.trim()) {
    message = detail.trim();
  } else if (detail && typeof detail === 'object') {
    if (typeof detail.message === 'string' && detail.message.trim()) {
      message = detail.message.trim();
    } else if (Array.isArray(detail)) {
      // Pydantic 422 — list of validation errors.
      message = detail
        .map(d => `${(d.loc ?? []).join('.')} — ${d.msg}`)
        .join('; ');
    }
  } else if (typeof err?.message === 'string' && err.message.trim()) {
    message = err.message.trim();
  }

  // Prepend HTTP status so the banner reads like "500 — no such table".
  const prefix = status > 0 ? `${status} — ` : '';
  const display = `${prefix}${message}`;

  // Optional verbose detail block. Includes findings array when present.
  const lines: string[] = [display];
  if (detail && typeof detail === 'object' && Array.isArray(detail.findings) && detail.findings.length) {
    lines.push(...detail.findings.map((f: string) => `  • ${f}`));
  }
  if (status === 0) {
    lines.push('No response from the backend. Most common causes:');
    lines.push('  1. uvicorn crashed or never started — check the backend terminal for an import error.');
    lines.push('  2. Missing dependency — run `pip install -r backend/requirements.txt` (sqlglot was added recently).');
    lines.push('  3. Frontend running on a port not in CORS_ORIGINS — add it to backend/.env.');
    lines.push('  4. Quick test: `curl http://localhost:8000/api/v1/kpi/healthz` should return 200.');
  } else if (status === 500) {
    lines.push('Backend error — check the server logs. If this is your first run, did you run `alembic upgrade head`?');
  } else if (status === 401) {
    lines.push('Your session may have expired. Try logging in again.');
  } else if (status === 403) {
    lines.push('Your role does not have permission. KPI Studio is currently SuperAdmin-only.');
  } else if (status === 404) {
    lines.push('Endpoint not found. The kpi_studio router may not be mounted — check backend startup logs.');
  }

  return {
    message: display,
    detail: lines.join('\n'),
    status,
  };
}
