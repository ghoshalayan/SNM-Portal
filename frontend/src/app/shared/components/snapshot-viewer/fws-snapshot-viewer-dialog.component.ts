/**
 * Read-only FWS (Final Working Sheet) snapshot viewer.
 *
 * Renders the frozen FWS snapshot in the same line-items layout the
 * user sees on the live FWS tab — same columns, same cost-head
 * groupings, but no editing affordances. Reviewers use this from the
 * version picker to confirm what was approved at a given point in
 * the cycle.
 *
 * Blob shape: a flat array of line-row objects (no wrapper). Each row
 * has item identity, the 22 cost heads, dispatch mode, and totals.
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

const FWS_COLS: ColMeta[] = [
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
  { key: 'modeOfDispatch', label: 'Dispatch', width: '120px' },
];

export interface FwsSnapshotViewerDialogData {
  url: string;
  title: string;
  /** Optional footer line — e.g. "follows C1-V1" or "cycle C2". */
  sourceText?: string | null;
}

interface FwsSnapshotDetail {
  snapshotId: number;
  versionNo: number;
  approvedAt?: string;
  approvedByName?: string;
  label?: string;
  /** Flat array of line rows. */
  snapshot: Record<string, any>[];
}

@Component({
  selector: 'app-fws-snapshot-viewer-dialog',
  standalone: true,
  imports: [
    CommonModule, DatePipe,
    MatButtonModule, MatDialogModule, MatIconModule, MatProgressSpinnerModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="title-icon">inventory_2</mat-icon>
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
          @if (detail.approvedAt) {
            <span class="meta-when">Approved {{ detail.approvedAt | date: 'dd MMM yyyy, HH:mm' }}</span>
          }
          @if (detail.approvedByName) {
            <span class="meta-who">by {{ detail.approvedByName }}</span>
          }
          <span class="meta-count">{{ rows.length }} line{{ rows.length === 1 ? '' : 's' }}</span>
        </div>

        @if (rows.length === 0) {
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
                        [class.totrate]="c.key === 'totRate'">
                      {{ c.label }}
                    </th>
                  }
                </tr>
              </thead>
              <tbody>
                @for (row of rows; track $index; let i = $index) {
                  <tr>
                    @for (c of cols; track c.key) {
                      <td [class.num]="c.num"
                          [class.neg]="c.neg"
                          [class.deducted]="c.deducted"
                          [class.totrate]="c.key === 'totRate'">
                        {{ display(row, c, i + 1) }}
                      </td>
                    }
                  </tr>
                }
              </tbody>
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
      margin-bottom: 12px;
      background: var(--snm-bg-panel);
      border-radius: 6px;
      font-size: 12px;
      color: var(--snm-text-secondary);
    }
    .meta-chip strong { font-size: 13px; color: var(--snm-text-primary); }
    .meta-when { font-variant-numeric: tabular-nums; }
    .meta-who { font-style: italic; }
    .meta-count { margin-left: auto; color: var(--snm-text-muted); }

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
    table.snap-table {
      width: 100%;
      border-collapse: collapse;
    }
    .snap-table th, .snap-table td {
      border: 1px solid var(--snm-border-divider);
      padding: 6px 10px;
      white-space: nowrap;
      text-align: center;
    }
    .snap-table td {
      font-size: 13px;
      color: var(--snm-text-primary);
    }
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
export class FwsSnapshotViewerDialogComponent implements OnInit {
  detail: FwsSnapshotDetail | null = null;
  loading = true;
  error: string | null = null;
  cols = FWS_COLS;
  rows: Record<string, any>[] = [];

  private fmt = new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  constructor(
    private api: ApiService,
    public dialogRef: MatDialogRef<FwsSnapshotViewerDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: FwsSnapshotViewerDialogData,
  ) {}

  ngOnInit(): void {
    this.api.get<FwsSnapshotDetail>(this.data.url).subscribe({
      next: (res) => {
        this.detail = res;
        const raw = Array.isArray(res?.snapshot) ? res.snapshot : [];
        this.rows = raw.filter((r: any) => r && r['isActive'] !== false);
        this.loading = false;
      },
      error: (e) => {
        this.error = e?.error?.detail || e?.error?.message || 'Failed to load snapshot.';
        this.loading = false;
      },
    });
  }

  display(row: any, col: ColMeta, sno: number): string {
    if (col.key === '_sno') return String(sno);
    if (col.key === '_gst') {
      const t = Number(row.totRate || 0);
      return t ? this.fmt.format(t * 0.18) : '';
    }
    const v = row[col.key];
    if (v == null || v === '') return '';
    if (col.num) {
      const n = Number(v);
      return isFinite(n) ? this.fmt.format(n) : String(v);
    }
    return String(v);
  }

  downloadCsv(): void {
    if (!this.detail) return;
    const header = this.cols.map(c => c.label).join(',');
    const lines = this.rows.map((r, i) =>
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
    a.download = `fws-${this.data.title.replace(/[^\w-]+/g, '_')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  close(): void {
    this.dialogRef.close();
  }
}
