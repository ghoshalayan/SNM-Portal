/**
 * Read-only Viability Sheet snapshot viewer.
 *
 * Renders the frozen viability snapshot in the same shape the user
 * sees on the live Viability tab — the adjusted sheet with cost
 * heads, ordered qty, and gross totals. Reviewers use this from the
 * version picker to confirm what was approved.
 *
 * Blob shape: { sheet: {...header...}, lines: [{...row fields...}] }.
 * We do NOT render the original working sheet alongside (it's not in
 * the snapshot); the FWS picker is the right place to inspect that.
 */
import { CommonModule, DatePipe } from '@angular/common';
import { Component, Inject, OnInit } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { ApiService } from '../../../core/services/api.service';
import {
  ADJUSTABLE_HEADS,
  HEAD_LABEL,
} from '../../../features/quotations/quotation-viability/goal-seek-dialog.component';

const COST_HEADS = ['TPWGST', ...ADJUSTABLE_HEADS];
const NEGATIVE_KEYS = new Set(['CD', 'ShortLnthCharge', 'SplDisc']);
const DEDUCTED_KEYS = new Set(['CD', 'SplDisc']);

interface ColMeta {
  key: string;
  label: string;
  width: string;
  num?: boolean;
  neg?: boolean;
  deducted?: boolean;
  gross?: boolean;
}

function headCol(key: string): ColMeta {
  return {
    key,
    label: HEAD_LABEL[key] || key,
    width: '90px',
    num: true,
    neg: NEGATIVE_KEYS.has(key),
    deducted: DEDUCTED_KEYS.has(key),
  };
}

const VIABILITY_COLS: ColMeta[] = [
  { key: '_sno', label: '#', width: '44px' },
  { key: 'itemName', label: 'Item', width: '150px' },
  { key: 'itemGradeName', label: 'Grade', width: '110px' },
  { key: 'itemDia', label: 'Dia', width: '70px' },
  { key: 'itemLength', label: 'Length', width: '90px' },
  { key: 'quantity', label: 'Qty', width: '70px', num: true },
  ...COST_HEADS.map(headCol),
  { key: 'totRate', label: 'Total Rs/MT', width: '110px', num: true },
  { key: '_gst', label: 'GST @ 18%', width: '90px', num: true },
  { key: 'totAmount', label: 'EX/FOR Price', width: '110px', num: true },
  { key: 'orderedQty', label: 'Ordered Qty (MT)', width: '110px', num: true, gross: true },
  { key: 'totalAmount', label: 'Total Amount', width: '120px', num: true, gross: true },
  { key: 'totalGst', label: 'Total GST', width: '110px', num: true, gross: true },
  { key: 'grossExForPrice', label: 'Gross EX/FOR', width: '120px', num: true, gross: true },
  { key: 'modeOfDispatch', label: 'Dispatch', width: '120px' },
];

export interface ViabilitySnapshotViewerDialogData {
  url: string;
  title: string;
  /** Optional footer line — typically "from FWS V<n>". */
  sourceText?: string | null;
}

interface ViabilitySnapshotDetail {
  snapshotId: number;
  versionNo: number;
  approvedAt?: string;
  approvedByName?: string;
  label?: string;
  snapshot: {
    sheet: Record<string, any>;
    lines: Record<string, any>[];
  };
}

@Component({
  selector: 'app-viability-snapshot-viewer-dialog',
  standalone: true,
  imports: [
    CommonModule, DatePipe,
    MatButtonModule, MatDialogModule, MatIconModule, MatProgressSpinnerModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="title-icon">query_stats</mat-icon>
      {{ data.title }}
    </h2>

    <mat-dialog-content class="content">
      @if (loading) {
        <div class="snap-loading">
          <mat-spinner diameter="32"></mat-spinner>
          <span>Loading snapshot…</span>
        </div>
      } @else if (error) {
        <div class="snap-error">
          <mat-icon>error_outline</mat-icon>
          <span>{{ error }}</span>
        </div>
      } @else if (detail) {
        <div class="meta-strip">
          <span class="meta-chip"><strong>V{{ detail.versionNo }}</strong></span>
          @if (sheet?.status) {
            <span class="status-pill" [class.is-approved]="sheet.status === 'Approved'">
              {{ sheet.status }}
            </span>
          }
          @if (detail.approvedAt) {
            <span class="meta-when">Approved {{ detail.approvedAt | date: 'dd MMM yyyy, HH:mm' }}</span>
          }
          @if (detail.approvedByName) {
            <span class="meta-who">by {{ detail.approvedByName }}</span>
          }
          <span class="meta-count">{{ lines.length }} line{{ lines.length === 1 ? '' : 's' }}</span>
        </div>

        @if (sheet?.tpCostMode) {
          <div class="tp-strip">
            <mat-icon class="tp-icon">payments</mat-icon>
            <span><strong>TP Cost source:</strong>
              @if (sheet.tpCostMode === 'po_working_sheet' || sheet.tpCostMode === 'approved_date') {
                LTP on PO Final Working Sheet
              } @else {
                As of {{ sheet.tpCostAsOfDate ? (sheet.tpCostAsOfDate | date: 'dd MMM yyyy') : 'today' }}
              }
            </span>
          </div>
        }

        @if (lines.length === 0) {
          <div class="empty-state">
            <mat-icon>inbox</mat-icon>
            <p>This snapshot has no line items.</p>
          </div>
        } @else {
          <div class="table-wrap">
            <table class="snap-table">
              <thead>
                <tr>
                  @for (c of cols; track c.key) {
                    <th [style.min-width]="c.width"
                        [class.neg]="c.neg"
                        [class.deducted]="c.deducted"
                        [class.gross]="c.gross"
                        [class.totrate]="c.key === 'totRate'">
                      {{ c.label }}
                    </th>
                  }
                </tr>
              </thead>
              <tbody>
                @for (row of lines; track $index; let i = $index) {
                  <tr>
                    @for (c of cols; track c.key) {
                      <td [class.num]="c.num"
                          [class.neg]="c.neg"
                          [class.deducted]="c.deducted"
                          [class.gross]="c.gross"
                          [class.totrate]="c.key === 'totRate'">
                        {{ display(row, c, i + 1) }}
                      </td>
                    }
                  </tr>
                }
              </tbody>
              <tfoot>
                <tr class="totals-row">
                  <td colspan="6" class="left"><strong>Totals</strong></td>
                  <td [attr.colspan]="cols.length - 6 - 4"></td>
                  <td class="num gross"><strong>{{ fmt(totalOrderedQty) }}</strong></td>
                  <td class="num gross"><strong>{{ fmt(totalAmount) }}</strong></td>
                  <td class="num gross"><strong>{{ fmt(totalGst) }}</strong></td>
                  <td class="num gross"><strong>{{ fmt(grossExForPrice) }}</strong></td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>
        }

        @if (data.sourceText) {
          <div class="source-footer">
            <mat-icon>subdirectory_arrow_right</mat-icon>
            <span>{{ data.sourceText }}</span>
          </div>
        }
      }
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      @if (detail) {
        <button mat-stroked-button (click)="downloadCsv()">
          <mat-icon>download</mat-icon> Download CSV
        </button>
      }
      <button mat-raised-button color="primary" (click)="close()">Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host { display: block; }
    .title-icon { vertical-align: middle; margin-right: 6px; color: var(--snm-accent); }
    .content {
      min-width: 80vw;
      max-width: 92vw;
      max-height: 70vh;
      overflow: auto;
      padding-top: 6px;
    }
    .snap-loading, .snap-error {
      display: flex; align-items: center; gap: 10px;
      padding: 24px;
      color: var(--snm-text-muted);
      font-size: 13px;
    }
    .snap-error mat-icon { color: var(--snm-error); }

    .meta-strip {
      display: flex; flex-wrap: wrap; align-items: center; gap: 12px;
      padding: 8px 12px;
      margin-bottom: 8px;
      background: var(--snm-bg-panel);
      border-radius: 6px;
      font-size: 12px;
      color: var(--snm-text-secondary);
    }
    .meta-chip strong { font-size: 13px; color: var(--snm-text-primary); }
    .status-pill {
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 10px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.4px;
      background: rgba(200, 150, 30, 0.18);
      color: rgba(160, 110, 0, 0.95);
    }
    .status-pill.is-approved {
      background: rgba(58, 107, 181, 0.12);
      color: var(--snm-accent-dark);
    }
    .meta-when { font-variant-numeric: tabular-nums; }
    .meta-who { font-style: italic; }
    .meta-count { margin-left: auto; color: var(--snm-text-muted); }

    .tp-strip {
      display: flex; align-items: center; gap: 8px;
      padding: 8px 12px;
      margin-bottom: 12px;
      background: var(--snm-bg-card);
      border: 1px solid var(--snm-border-divider);
      border-radius: 6px;
      font-size: 12px;
      color: var(--snm-text-secondary);
    }
    .tp-strip .tp-icon {
      color: var(--snm-accent);
      font-size: 18px; width: 18px; height: 18px;
    }

    .empty-state {
      display: flex; flex-direction: column; align-items: center;
      padding: 32px;
      color: var(--snm-text-muted);
      gap: 6px;
    }
    .empty-state mat-icon { font-size: 36px; width: 36px; height: 36px; opacity: 0.55; }

    .table-wrap {
      overflow-x: auto;
      border: 1px solid var(--snm-border-divider);
      border-radius: 8px;
      margin-bottom: 8px;
    }
    table.snap-table { width: 100%; border-collapse: collapse; }
    .snap-table th, .snap-table td {
      border: 1px solid var(--snm-border-divider);
      padding: 6px 10px;
      white-space: nowrap;
      text-align: center;
    }
    .snap-table td { font-size: 13px; color: var(--snm-text-primary); }
    .snap-table th {
      background: var(--snm-bg-header-row);
      color: var(--snm-text-secondary);
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.3px;
      position: sticky; top: 0; z-index: 1;
    }
    .snap-table td.num, .snap-table th.num {
      text-align: right; font-variant-numeric: tabular-nums;
    }
    .snap-table .neg { color: #ef5350; }
    .snap-table th.deducted {
      background: rgba(229, 57, 53, 0.18) !important;
      color: #c62828 !important;
    }
    .snap-table td.deducted {
      background: rgba(229, 57, 53, 0.08);
      color: #c62828 !important;
      font-weight: 500;
    }
    .snap-table .gross { background: rgba(255, 242, 204, 0.35); }
    .snap-table th.totrate {
      background: var(--snm-accent-subtle) !important;
      color: var(--snm-accent-dark);
      font-weight: 700;
    }
    .snap-table td.totrate {
      background: var(--snm-accent-subtle);
      color: var(--snm-accent-dark);
      font-weight: 600;
    }
    .snap-table tr.totals-row td {
      background: var(--snm-accent-subtle);
      border-top: 2px solid var(--snm-accent);
      color: var(--snm-accent-dark);
    }
    .snap-table tr.totals-row td.left { text-align: left; }

    .source-footer {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 6px 10px;
      font-size: 12px;
      color: var(--snm-accent-dark);
      font-style: italic;
      background: var(--snm-bg-panel);
      border-radius: 4px;
    }
    .source-footer mat-icon { font-size: 16px; width: 16px; height: 16px; color: var(--snm-accent); }
  `],
})
export class ViabilitySnapshotViewerDialogComponent implements OnInit {
  detail: ViabilitySnapshotDetail | null = null;
  loading = true;
  error: string | null = null;
  cols = VIABILITY_COLS;
  sheet: any = null;
  lines: any[] = [];

  totalOrderedQty = 0;
  totalAmount = 0;
  totalGst = 0;
  grossExForPrice = 0;

  private nf = new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  constructor(
    private api: ApiService,
    public dialogRef: MatDialogRef<ViabilitySnapshotViewerDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: ViabilitySnapshotViewerDialogData,
  ) {}

  ngOnInit(): void {
    this.api.get<ViabilitySnapshotDetail>(this.data.url).subscribe({
      next: (res) => {
        this.detail = res;
        const blob = res?.snapshot || ({} as any);
        this.sheet = blob.sheet || null;
        const raw = Array.isArray(blob.lines) ? blob.lines : [];
        this.lines = raw.filter((l: any) => l && l['isActive'] !== false);
        this.computeTotals();
        this.loading = false;
      },
      error: (e) => {
        this.error = e?.error?.detail || e?.error?.message || 'Failed to load snapshot.';
        this.loading = false;
      },
    });
  }

  private computeTotals(): void {
    this.totalOrderedQty = this.sum('orderedQty');
    this.totalAmount = this.sum('totalAmount');
    this.totalGst = this.sum('totalGst');
    this.grossExForPrice = this.sum('grossExForPrice');
  }

  private sum(key: string): number {
    return this.lines.reduce((s, l) => s + (Number(l[key]) || 0), 0);
  }

  fmt(n: number): string {
    if (!isFinite(n) || n === 0) return n === 0 ? '0.00' : '';
    return this.nf.format(n);
  }

  display(row: any, col: ColMeta, sno: number): string {
    if (col.key === '_sno') return String(sno);
    if (col.key === '_gst') {
      const t = Number(row.totRate || 0);
      return t ? this.nf.format(t * 0.18) : '';
    }
    const v = row[col.key];
    if (v == null || v === '') return '';
    if (col.num) {
      const n = Number(v);
      return isFinite(n) ? this.nf.format(n) : String(v);
    }
    return String(v);
  }

  downloadCsv(): void {
    if (!this.detail) return;
    const header = this.cols.map(c => c.label).join(',');
    const lines = this.lines.map((r, i) =>
      this.cols.map(c => {
        const v = this.display(r, c, i + 1);
        return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
      }).join(',')
    );
    const csv = [header, ...lines].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `viability-${this.data.title.replace(/[^\w-]+/g, '_')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  close(): void {
    this.dialogRef.close();
  }
}
