import {
  ChangeDetectionStrategy, Component, Inject, computed, signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  MAT_DIALOG_DATA, MatDialogModule, MatDialogRef,
} from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDividerModule } from '@angular/material/divider';

/**
 * Reusable preview modal (CR #3) for the Working Sheet, Final Working
 * Sheet, and Viability Sheet. Caller supplies columns + rows; the
 * dialog handles:
 *   - Hide-blank-columns toggle (default ON) — drops columns where
 *     every row's value is null / undefined / 0 / "".
 *   - Print — opens the browser print dialog scoped to the preview.
 *   - Excel — delegates back to the caller via the onExportExcel hook
 *     so each sheet can reuse its existing exporter.
 *   - Close — dismisses the dialog.
 */

export type PreviewCellFormat = 'text' | 'number' | 'integer';

export interface SheetPreviewColumn {
  key: string;
  label: string;
  format?: PreviewCellFormat;
  /** Optional cell-class for visual cues (e.g. 'right', 'neg'). */
  cellClass?: string;
}

export interface SheetPreviewDialogData {
  title: string;
  /** Free-text caption shown above the table (e.g. quotation no, version). */
  caption?: string;
  columns: SheetPreviewColumn[];
  rows: any[];
  /** When true, the hide-blank-columns toggle starts in the "hide" state. */
  hideBlankByDefault?: boolean;
  /** Caller hook for Excel export. Falsy → Excel button hidden. */
  onExportExcel?: () => void;
}

@Component({
  selector: 'app-sheet-preview-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    MatDialogModule, MatButtonModule, MatIconModule,
    MatSlideToggleModule, MatTooltipModule, MatDividerModule,
  ],
  template: `
    <h2 mat-dialog-title class="title-row">
      <mat-icon class="title-icon">visibility</mat-icon>
      <div class="title-text">
        <span class="t-main">{{ data.title }}</span>
        <span class="t-sub" *ngIf="data.caption">{{ data.caption }}</span>
      </div>
      <span class="spacer"></span>
      <mat-slide-toggle color="primary"
                        [checked]="hideBlank()"
                        (change)="hideBlank.set($event.checked)"
                        matTooltip="Hide columns where every row is blank or zero">
        Hide blank columns
      </mat-slide-toggle>
    </h2>

    <mat-dialog-content class="content">
      <div class="preview-host" id="preview-host">
        <table class="preview-table">
          <thead>
            <tr>
              <th class="col-sno">#</th>
              <th *ngFor="let c of visibleColumns()"
                  [class]="c.cellClass || ''">
                {{ c.label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let row of data.rows; let i = index">
              <td class="col-sno">{{ i + 1 }}</td>
              <td *ngFor="let c of visibleColumns()"
                  [class]="c.cellClass || ''"
                  [class.num]="c.format === 'number' || c.format === 'integer'">
                {{ formatCell(row, c) }}
              </td>
            </tr>
            <tr *ngIf="!data.rows.length">
              <td class="empty" [attr.colspan]="visibleColumns().length + 1">
                No rows to preview.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </mat-dialog-content>

    <mat-dialog-actions align="end" class="actions">
      <span class="footnote">
        {{ visibleColumns().length }} of {{ data.columns.length }} columns shown
        @if (hiddenCount(); as h) {
          <span *ngIf="h > 0"> · {{ h }} hidden</span>
        }
      </span>
      <span class="spacer"></span>
      <button mat-stroked-button *ngIf="data.onExportExcel" (click)="data.onExportExcel!()">
        <mat-icon>table_view</mat-icon> Excel
      </button>
      <button mat-flat-button color="primary" mat-dialog-close>Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host { display: block; }
    .title-row {
      display: flex; align-items: center; gap: 10px;
      margin: 0 !important;
    }
    .title-icon { color: var(--snm-accent); }
    .title-text { display: flex; flex-direction: column; gap: 2px; }
    .t-main { font-size: 1.05rem; font-weight: 600; color: var(--snm-text-primary); }
    .t-sub { font-size: 0.75rem; color: var(--snm-text-muted); font-weight: 400; }
    .spacer { flex: 1; }
    .content {
      max-height: 70vh;
      min-width: 720px;
      max-width: 95vw;
      padding-top: 8px !important;
    }
    /* Preview always renders on white paper (WYSIWYG-of-print). */
    .preview-host {
      background: #fff;
      color: #1a1a1a;
      border: 1px solid #d0d0d0;
      border-radius: 4px;
      padding: 12px;
      overflow-x: auto;
    }
    .preview-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      color: #1a1a1a;
    }
    .preview-table th, .preview-table td {
      padding: 5px 8px;
      border-bottom: 1px solid #e0e0e0;
      white-space: nowrap;
    }
    .preview-table thead tr {
      background: #1565c0;
      color: #fff;
    }
    .preview-table thead th { font-weight: 600; }
    .preview-table tbody tr:nth-child(even) { background: #f7f7f9; }
    .preview-table td.num,
    .preview-table th.num { text-align: right; font-variant-numeric: tabular-nums; }
    .preview-table td.neg, .preview-table th.neg { color: #c62828; }
    .preview-table .col-sno { width: 36px; text-align: center; }
    .preview-table .empty {
      text-align: center; padding: 24px; color: #888; font-style: italic;
    }
    .actions {
      padding: 8px 16px 12px;
      align-items: center;
    }
    .footnote { font-size: 12px; color: var(--snm-text-muted); }

    /* When the user prints, only the preview table reaches the page. */
    @media print {
      :host { display: contents; }
    }
  `],
})
export class SheetPreviewDialogComponent {
  readonly hideBlank = signal(true);

  /** Columns that survive the hide-blank filter. */
  readonly visibleColumns = computed(() => {
    if (!this.hideBlank()) return this.data.columns;
    const rows = this.data.rows;
    return this.data.columns.filter(c => rows.some(r => !this.isBlank(r[c.key])));
  });

  readonly hiddenCount = computed(() =>
    this.data.columns.length - this.visibleColumns().length,
  );

  constructor(
    private dialogRef: MatDialogRef<SheetPreviewDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: SheetPreviewDialogData,
  ) {
    if (data.hideBlankByDefault === false) this.hideBlank.set(false);
  }

  private isBlank(v: any): boolean {
    if (v == null) return true;
    if (typeof v === 'number') return v === 0;
    if (typeof v === 'string') {
      const trimmed = v.trim();
      if (trimmed === '') return true;
      // Pydantic v2 serializes Decimal columns (viability cost heads,
      // totRate, etc.) as JSON strings — "0.00", "0", "0.000" all
      // mean "blank" for the hide-blank-columns toggle. Anything that
      // parses to a non-zero number is real data; non-numeric strings
      // (item name, dispatch mode) are real data too.
      const n = Number(trimmed);
      return Number.isFinite(n) && n === 0;
    }
    return false;
  }

  formatCell(row: any, col: SheetPreviewColumn): string {
    const v = row[col.key];
    if (v == null || v === '') return '';
    if (col.format === 'number') {
      const n = Number(v);
      if (Number.isNaN(n)) return String(v);
      return n.toLocaleString('en-IN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    }
    if (col.format === 'integer') {
      const n = Number(v);
      if (Number.isNaN(n)) return String(v);
      return n.toLocaleString('en-IN');
    }
    return String(v);
  }

}
