/**
 * Phase E — value formatting for chart values.
 *
 * Mirrors the ``BuilderFormat`` union on the backend. The chart
 * renderer reads ``chart_config.config.value_format`` (or
 * ``value_formats`` for stat groups) and dispatches here.
 *
 * Non-numeric inputs pass through unchanged so the same helper can
 * format strings, dates, and nulls without special-casing each
 * caller.
 */

export type ValueFormat = 'number' | 'currency' | 'percent' | 'short' | 'date' | 'text';

export interface FormatOptions {
  /** ISO 4217 code, e.g. ``'USD'`` / ``'INR'``. Falls back to the
   * locale's default currency when omitted. */
  currency?: string;
  /** Forces a fixed number of fractional digits. Auto when omitted. */
  decimals?: number;
}

/** Format a value for display. ``null`` / ``undefined`` / empty
 * strings render as an em-dash so a blank cell never looks like a
 * mistake. */
export function formatValue(
  v: unknown,
  fmt: ValueFormat | null | undefined = 'number',
  opts: FormatOptions = {},
): string {
  if (v == null || v === '') return '—';

  // ``date`` stays as the input — let the template's date pipe handle it.
  if (fmt === 'date') return String(v);

  // Non-numeric: render as text regardless of fmt request.
  const num = typeof v === 'number' ? v : Number(v);
  if (!Number.isFinite(num)) return String(v);

  switch (fmt) {
    case 'currency':
      return num.toLocaleString(undefined, {
        style: 'currency',
        currency: opts.currency ?? 'INR',
        minimumFractionDigits: opts.decimals ?? 0,
        maximumFractionDigits: opts.decimals ?? 2,
      });

    case 'percent':
      // Inputs in [0, 1] render as 0%–100%; inputs > 1 are treated
      // as already a percentage (so ``42`` → ``42%``).
      return (Math.abs(num) <= 1 ? num * 100 : num).toLocaleString(undefined, {
        minimumFractionDigits: opts.decimals ?? 0,
        maximumFractionDigits: opts.decimals ?? 1,
      }) + '%';

    case 'short':
      return shortNumber(num, opts.decimals ?? 1);

    case 'text':
      return String(v);

    case 'number':
    default: {
      const max = opts.decimals ?? (Number.isInteger(num) ? 0 : 2);
      return num.toLocaleString(undefined, {
        minimumFractionDigits: opts.decimals ?? 0,
        maximumFractionDigits: max,
      });
    }
  }
}

/** ``1234`` → ``1.2K``, ``1_500_000`` → ``1.5M``, ``2.4e9`` → ``2.4B``.
 * Handles negatives and tiny values gracefully (sub-1000 just formats
 * with the requested decimal precision). */
export function shortNumber(n: number, decimals = 1): string {
  if (!Number.isFinite(n)) return String(n);
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs < 1_000) {
    return sign + abs.toLocaleString(undefined, {
      maximumFractionDigits: Number.isInteger(abs) ? 0 : decimals,
    });
  }
  const tiers: Array<[number, string]> = [
    [1_000_000_000_000, 'T'],
    [1_000_000_000, 'B'],
    [1_000_000, 'M'],
    [1_000, 'K'],
  ];
  for (const [factor, suffix] of tiers) {
    if (abs >= factor) {
      const scaled = abs / factor;
      // Drop the decimal when the scaled value is already round
      // (1.0K → 1K) so the labels stay tight.
      const rounded = scaled.toFixed(decimals);
      const trimmed = rounded.endsWith('0'.repeat(decimals))
        ? Math.round(scaled).toString()
        : rounded;
      return sign + trimmed + suffix;
    }
  }
  return sign + abs.toString();
}
