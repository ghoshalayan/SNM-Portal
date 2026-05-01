import { NativeDateAdapter, MatDateFormats } from '@angular/material/core';

/**
 * Custom date adapter that forces `dd-MM-yyyy` for the datepicker input
 * (display + parse) while keeping NativeDateAdapter's locale-aware
 * behaviour for calendar headers and a11y labels.
 *
 * Used together with SNM_DATE_FORMATS below — the `dateInput` key uses the
 * sentinel string `'input'` which routes through this adapter's overridden
 * `format()` / `parse()` for dash-separated text. All other format keys
 * pass through standard Intl options.
 */
export class SnmDateAdapter extends NativeDateAdapter {
  override format(date: Date, displayFormat: any): string {
    if (displayFormat === 'input') {
      const d = String(date.getDate()).padStart(2, '0');
      const m = String(date.getMonth() + 1).padStart(2, '0');
      const y = date.getFullYear();
      return `${d}-${m}-${y}`;
    }
    return super.format(date, displayFormat);
  }

  override parse(value: any): Date | null {
    if (typeof value === 'string') {
      // Accept dd-MM-yyyy and dd/MM/yyyy as a forgiveness gesture for users
      // pasting from older docs. Rejects everything else by falling through.
      const m = /^(\d{1,2})[-\/](\d{1,2})[-\/](\d{4})$/.exec(value.trim());
      if (m) {
        const day = +m[1];
        const month = +m[2] - 1;
        const year = +m[3];
        const d = new Date(year, month, day);
        if (
          d.getFullYear() === year &&
          d.getMonth() === month &&
          d.getDate() === day
        ) {
          return d;
        }
      }
    }
    return super.parse(value);
  }
}

export const SNM_DATE_FORMATS: MatDateFormats = {
  parse: {
    dateInput: 'input',
  },
  display: {
    dateInput: 'input',
    monthYearLabel: { year: 'numeric', month: 'short' },
    dateA11yLabel: { year: 'numeric', month: 'long', day: 'numeric' },
    monthYearA11yLabel: { year: 'numeric', month: 'long' },
  },
};
