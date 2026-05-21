/**
 * Shared print-styling primitives. Used by both the quotation-print
 * component (renders the actual print) and the quotation-format dialog
 * (renders a live preview as the user edits).
 *
 * The model on the server stores these as nullable columns on
 * ``QuotationFormat``; this module resolves a partial server payload
 * against ``DEFAULT_PRINT_STYLE`` so consumers always get a complete,
 * non-null shape.
 */

export type Alignment = 'left' | 'center' | 'right';
export type RoundingMode = 'ceiling' | 'floor' | 'round';

export type ColumnId =
  | 'sno' | 'itemName' | 'grade' | 'dia' | 'length' | 'unit'
  | 'qty' | 'basicRate' | 'igst' | 'cgst' | 'sgst'
  | 'finalPrice' | 'modeOfDispatch';

export interface ColumnAlignment {
  header: Alignment;
  body: Alignment;
}

export interface PrintStyle {
  headerBgColor: string;
  headerTextColor: string;
  roundingMode: RoundingMode;
  amountDecimals: number;
  taxDecimals: number;
  taxShowPercent: boolean;
  qtyDecimals: number;
  dimensionDecimals: number;
  columnAlignments: Record<ColumnId, ColumnAlignment>;
}

/** Fallback values applied whenever the server returns NULL for a field
 *  or the user clicks "Reset to defaults". Locked by the user:
 *  blue header / white text / 0 decimals / ceiling rounding /
 *  numerics right-aligned + sequence & text columns centered. */
export const DEFAULT_PRINT_STYLE: PrintStyle = {
  headerBgColor: '#1565c0',
  headerTextColor: '#FFFFFF',
  roundingMode: 'ceiling',
  amountDecimals: 0,
  taxDecimals: 0,
  taxShowPercent: false,
  qtyDecimals: 0,
  dimensionDecimals: 0,
  columnAlignments: {
    sno:            { header: 'center', body: 'center' },
    itemName:       { header: 'center', body: 'center' },
    grade:          { header: 'center', body: 'center' },
    dia:            { header: 'right',  body: 'right'  },
    length:         { header: 'right',  body: 'right'  },
    unit:           { header: 'center', body: 'center' },
    qty:            { header: 'right',  body: 'right'  },
    basicRate:      { header: 'right',  body: 'right'  },
    igst:           { header: 'right',  body: 'right'  },
    cgst:           { header: 'right',  body: 'right'  },
    sgst:           { header: 'right',  body: 'right'  },
    finalPrice:     { header: 'right',  body: 'right'  },
    modeOfDispatch: { header: 'center', body: 'center' },
  },
};

/** Display labels for the column-alignment grid in the format editor. */
export const COLUMN_LABELS: Record<ColumnId, string> = {
  sno: 'Serial No.',
  itemName: 'Item Name',
  grade: 'Grade',
  dia: 'Dia',
  length: 'Length',
  unit: 'Unit',
  qty: 'Qty',
  basicRate: 'Basic Rate',
  igst: 'IGST %',
  cgst: 'CGST %',
  sgst: 'SGST %',
  finalPrice: 'Final Price / MT',
  modeOfDispatch: 'Mode of Dispatch',
};

/** Order columns appear in the format-editor alignment grid. */
export const COLUMN_ORDER: ColumnId[] = [
  'sno', 'itemName', 'grade', 'dia', 'length', 'unit',
  'qty', 'basicRate', 'igst', 'cgst', 'sgst',
  'finalPrice', 'modeOfDispatch',
];

/** Lenient input shape — every field nullable so server payloads
 *  (where any column may be NULL post-migration) pass through cleanly
 *  without forced `as any` casts at call sites. */
export interface PrintStyleInput {
  headerBgColor?: string | null;
  headerTextColor?: string | null;
  roundingMode?: RoundingMode | string | null;
  amountDecimals?: number | null;
  taxDecimals?: number | null;
  taxShowPercent?: boolean | null;
  qtyDecimals?: number | null;
  dimensionDecimals?: number | null;
  columnAlignments?: string | Record<string, ColumnAlignment> | null;
}

/** Resolve a partial server payload against the defaults. Accepts
 *  ``columnAlignments`` as either a JSON string (server shape) or an
 *  already-parsed object (in-memory form-bound state). */
export function resolvePrintStyle(
  fmt: PrintStyleInput | null | undefined,
): PrintStyle {
  const f = fmt ?? {};
  const aligns = parseAlignments(f.columnAlignments);
  return {
    headerBgColor: f.headerBgColor || DEFAULT_PRINT_STYLE.headerBgColor,
    headerTextColor: f.headerTextColor || DEFAULT_PRINT_STYLE.headerTextColor,
    roundingMode: (f.roundingMode as RoundingMode) || DEFAULT_PRINT_STYLE.roundingMode,
    amountDecimals: numOr(f.amountDecimals, DEFAULT_PRINT_STYLE.amountDecimals),
    taxDecimals: numOr(f.taxDecimals, DEFAULT_PRINT_STYLE.taxDecimals),
    taxShowPercent: f.taxShowPercent ?? DEFAULT_PRINT_STYLE.taxShowPercent,
    qtyDecimals: numOr(f.qtyDecimals, DEFAULT_PRINT_STYLE.qtyDecimals),
    dimensionDecimals: numOr(f.dimensionDecimals, DEFAULT_PRINT_STYLE.dimensionDecimals),
    columnAlignments: mergeAlignments(aligns),
  };
}

function numOr(v: number | null | undefined, fallback: number): number {
  return typeof v === 'number' && !Number.isNaN(v) ? v : fallback;
}

function parseAlignments(raw: unknown): Partial<Record<ColumnId, ColumnAlignment>> {
  if (!raw) return {};
  if (typeof raw === 'object') return raw as any;
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw);
      return typeof parsed === 'object' && parsed ? parsed : {};
    } catch {
      return {};
    }
  }
  return {};
}

function mergeAlignments(
  partial: Partial<Record<ColumnId, ColumnAlignment>>,
): Record<ColumnId, ColumnAlignment> {
  const out = {} as Record<ColumnId, ColumnAlignment>;
  for (const col of COLUMN_ORDER) {
    out[col] = {
      header: partial[col]?.header ?? DEFAULT_PRINT_STYLE.columnAlignments[col].header,
      body:   partial[col]?.body   ?? DEFAULT_PRINT_STYLE.columnAlignments[col].body,
    };
  }
  return out;
}

/** Round + format a number for print display using the configured
 *  rounding mode and decimal precision. Returns "" for null/undefined.
 *  Uses en-IN locale (1,23,457 grouping). */
export function formatPrintNumber(
  value: number | null | undefined,
  decimals: number,
  mode: RoundingMode,
): string {
  // Defence-in-depth: ``Number.isNaN`` only matches the numeric NaN
  // value — strings (including empty string and "NaN") slip past, then
  // get coerced inside ``applyRounding`` and resurface as the literal
  // text ``"NaN"`` via ``toLocaleString``. ``Number.isFinite(Number(x))``
  // also rejects Infinity / -Infinity / non-numeric strings, which is
  // what we want for currency / quantity / tax columns.
  const n = Number(value);
  if (value == null || !Number.isFinite(n)) return '';
  const rounded = applyRounding(n, decimals, mode);
  return rounded.toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Round a tax percentage and optionally append "%". Always returns
 *  the configured number of decimals so 18 → "18" / "18%" / "18.00".  */
export function formatTaxPercent(
  value: number | null | undefined,
  decimals: number,
  mode: RoundingMode,
  showPercent: boolean,
): string {
  const formatted = formatPrintNumber(value, decimals, mode);
  if (!formatted) return '';
  return showPercent ? `${formatted}%` : formatted;
}

function applyRounding(value: number, decimals: number, mode: RoundingMode): number {
  const f = Math.pow(10, decimals);
  switch (mode) {
    case 'ceiling': return Math.ceil(value * f) / f;
    case 'floor':   return Math.floor(value * f) / f;
    default:        return Math.round(value * f) / f;
  }
}
