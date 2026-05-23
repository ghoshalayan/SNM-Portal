/**
 * Read-only Annexure snapshot viewer.
 *
 * Renders the frozen annexure snapshot as a printable-style document
 * mirroring the section layout on the live Annexure tab — header
 * block (5 fields) + numbered points 1..27 grouped into Invoicing &
 * Transportation, Party Details, Quality, Misc + Signatures.
 *
 * Blob shape: { annexure: {...all annexure fields...} }.
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

interface FieldDef {
  key: string;
  label: string;
  /** "wide" = full row, "num" = numeric formatting, "date" = format as date. */
  wide?: boolean;
  num?: boolean;
  date?: boolean;
}

const HEADER_FIELDS: FieldDef[] = [
  { key: 'clientName', label: 'Client Name (A/C)', wide: true },
  { key: 'customerPONo', label: 'Customer PO No' },
  { key: 'customerPODate', label: 'PO Date', date: true },
  { key: 'totalBillableAmount', label: 'Total Billable Amount (₹)', num: true },
  { key: 'totalQuantityMT', label: 'Total Quantity (MT)', num: true },
  { key: 'addressedTo', label: 'Addressed To', wide: true },
];

const INVOICING_FIELDS: FieldDef[] = [
  { key: 'invoicing', label: '1. Invoicing' },
  { key: 'transportationMode', label: '2. Transportation' },
  { key: 'tcType', label: '3. TC Type' },
  { key: 'paymentTerms', label: '4. Payment Terms', wide: true },
  { key: 'loadabilityQty', label: '5. Loadability (MT / vehicle)', num: true },
  { key: 'transportChargesPerMT', label: '6. Transport Charges (₹/MT)', num: true },
  { key: 'transportChargesFOR', label: '7. Transportation FOR (Site)', wide: true },
  { key: 'specificLength', label: '8. Specific Length' },
  { key: 'tolerance', label: '9. Tolerance' },
  { key: 'deliverySchedule', label: '10. Delivery Schedule', wide: true },
  { key: 'transportRealizationPerMT', label: '11. Transport Realization (₹/MT)', num: true },
];

const PARTY_FIELDS: FieldDef[] = [
  { key: 'panNo', label: '12. PAN No' },
  { key: 'gstNo', label: '13. GST No' },
  { key: 'contactPerson', label: '14. Contact Person' },
  { key: 'contactPersonNumber', label: '15. Contact Number' },
  { key: 'billingAddress', label: '16. Billing Address', wide: true },
  { key: 'consigneeAddress', label: '17. Consignee Address', wide: true },
];

const QUALITY_FIELDS: FieldDef[] = [
  { key: 'qualityFe', label: '18. Quality (Fe)' },
  { key: 'qualityStandard', label: '19. Quality Standard' },
  { key: 'qualityStandardLength', label: '20. Std. Length' },
  { key: 'companyName', label: '21. Company (DGP)' },
];

const MISC_FIELDS: FieldDef[] = [
  { key: 'billsTo', label: '22. Bills To' },
  { key: 'totalOutstanding', label: '23. Total Outstanding (₹)', num: true },
  { key: 'overdueOutstanding', label: '24. Overdue Outstanding (₹)', num: true },
  { key: 'unloadingScope', label: '26. Unloading Scope' },
  { key: 'unloadingRate', label: '27. Unloading Rate (₹/MT)', num: true },
  { key: 'remarks', label: 'Remarks', wide: true },
];

const SIGNATURE_FIELDS: FieldDef[] = [
  { key: 'preparedByName', label: 'Prepared By' },
  { key: 'checkedByName', label: 'Checked By' },
  { key: 'approvedByName', label: 'Approved By' },
  { key: 'approvedon', label: 'Approved On', date: true },
];

export interface AnnexureSnapshotViewerDialogData {
  url: string;
  title: string;
  /** Optional footer line — typically "from Viability V<n> · PO <no>". */
  sourceText?: string | null;
}

interface AnnexureSnapshotDetail {
  snapshotId: number;
  versionNo: number;
  approvedAt?: string;
  approvedByName?: string;
  label?: string;
  snapshot: {
    annexure: Record<string, any>;
  };
}

interface DiaBreakupRow {
  dia?: string | number;
  qty?: string | number;
  rate?: string | number;
  amount?: string | number;
  [k: string]: any;
}

@Component({
  selector: 'app-annexure-snapshot-viewer-dialog',
  standalone: true,
  imports: [
    CommonModule, DatePipe,
    MatButtonModule, MatDialogModule, MatIconModule, MatProgressSpinnerModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="title-icon">description</mat-icon>
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
      } @else if (detail && ann) {
        <div class="meta-strip">
          <span class="meta-chip"><strong>V{{ detail.versionNo }}</strong></span>
          @if (ann.status) {
            <span class="status-pill" [class.is-approved]="ann.status === 'Approved'">
              {{ ann.status }}
            </span>
          }
          @if (detail.approvedAt) {
            <span class="meta-when">Approved {{ detail.approvedAt | date: 'dd MMM yyyy, HH:mm' }}</span>
          }
          @if (detail.approvedByName) {
            <span class="meta-who">by {{ detail.approvedByName }}</span>
          }
        </div>

        <section class="ann-section">
          <h3>Header Block</h3>
          <div class="ann-grid">
            @for (f of headerFields; track f.key) {
              <div class="ann-field" [class.wide]="f.wide">
                <span class="ann-label">{{ f.label }}</span>
                <span class="ann-value">{{ display(ann, f) }}</span>
              </div>
            }
          </div>
        </section>

        <section class="ann-section">
          <h3>Invoicing &amp; Transportation</h3>
          <div class="ann-grid">
            @for (f of invoicingFields; track f.key) {
              <div class="ann-field" [class.wide]="f.wide">
                <span class="ann-label">{{ f.label }}</span>
                <span class="ann-value">{{ display(ann, f) }}</span>
              </div>
            }
          </div>
        </section>

        <section class="ann-section">
          <h3>Party Details</h3>
          <div class="ann-grid">
            @for (f of partyFields; track f.key) {
              <div class="ann-field" [class.wide]="f.wide">
                <span class="ann-label">{{ f.label }}</span>
                <span class="ann-value">{{ display(ann, f) }}</span>
              </div>
            }
          </div>
        </section>

        <section class="ann-section">
          <h3>Quality</h3>
          <div class="ann-grid">
            @for (f of qualityFields; track f.key) {
              <div class="ann-field" [class.wide]="f.wide">
                <span class="ann-label">{{ f.label }}</span>
                <span class="ann-value">{{ display(ann, f) }}</span>
              </div>
            }
          </div>
        </section>

        @if (diaBreakup.length > 0) {
          <section class="ann-section">
            <h3>25. Dia-wise Breakup</h3>
            <div class="table-wrap">
              <table class="snap-table">
                <thead>
                  <tr>
                    @for (k of diaBreakupCols; track k) {
                      <th>{{ k }}</th>
                    }
                  </tr>
                </thead>
                <tbody>
                  @for (r of diaBreakup; track $index) {
                    <tr>
                      @for (k of diaBreakupCols; track k) {
                        <td>{{ r[k] }}</td>
                      }
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }

        <section class="ann-section">
          <h3>Misc &amp; Remarks</h3>
          <div class="ann-grid">
            @for (f of miscFields; track f.key) {
              <div class="ann-field" [class.wide]="f.wide">
                <span class="ann-label">{{ f.label }}</span>
                <span class="ann-value">{{ display(ann, f) }}</span>
              </div>
            }
          </div>
        </section>

        <section class="ann-section sig">
          <h3>Signatures</h3>
          <div class="ann-grid">
            @for (f of signatureFields; track f.key) {
              <div class="ann-field">
                <span class="ann-label">{{ f.label }}</span>
                <span class="ann-value">{{ display(ann, f) }}</span>
              </div>
            }
          </div>
        </section>

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
        <button mat-stroked-button (click)="printSnapshot()">
          <mat-icon>print</mat-icon> Print
        </button>
        <button mat-stroked-button (click)="downloadJson()">
          <mat-icon>download</mat-icon> Download JSON
        </button>
      }
      <button mat-raised-button color="primary" (click)="close()">Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host { display: block; }
    .title-icon { vertical-align: middle; margin-right: 6px; color: var(--snm-accent); }
    .content {
      min-width: 720px;
      max-width: 900px;
      max-height: 75vh;
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

    .ann-section {
      margin-bottom: 16px;
      padding: 12px 14px;
      background: var(--snm-bg-card);
      border: 1px solid var(--snm-border-divider);
      border-radius: 8px;
    }
    .ann-section h3 {
      margin: 0 0 10px 0;
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      color: var(--snm-accent-dark);
    }
    .ann-section.sig {
      background: var(--snm-bg-panel);
    }

    .ann-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 16px;
    }

    .ann-field {
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: 6px 8px;
      background: var(--snm-bg-panel);
      border-left: 3px solid var(--snm-accent-shadow);
      border-radius: 4px;
      min-width: 0;
    }
    .ann-field.wide { grid-column: 1 / -1; }
    .ann-label {
      font-size: 11px;
      color: var(--snm-text-muted);
      text-transform: uppercase;
      letter-spacing: 0.3px;
      font-weight: 600;
    }
    .ann-value {
      font-size: 13px;
      color: var(--snm-text-primary);
      font-weight: 500;
      word-break: break-word;
      white-space: pre-wrap;
      min-height: 16px;
    }
    .ann-value:empty::before {
      content: '—';
      color: var(--snm-text-faint);
      font-style: italic;
    }

    .table-wrap {
      overflow-x: auto;
      border: 1px solid var(--snm-border-divider);
      border-radius: 6px;
    }
    table.snap-table {
      width: 100%; border-collapse: collapse; font-size: 12px;
    }
    .snap-table th, .snap-table td {
      border: 1px solid var(--snm-border-divider);
      padding: 4px 8px;
      text-align: left;
    }
    .snap-table th {
      background: var(--snm-bg-header-row);
      color: var(--snm-text-secondary);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 11px;
      letter-spacing: 0.3px;
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
export class AnnexureSnapshotViewerDialogComponent implements OnInit {
  detail: AnnexureSnapshotDetail | null = null;
  loading = true;
  error: string | null = null;

  ann: any = null;
  diaBreakup: DiaBreakupRow[] = [];
  diaBreakupCols: string[] = [];

  headerFields = HEADER_FIELDS;
  invoicingFields = INVOICING_FIELDS;
  partyFields = PARTY_FIELDS;
  qualityFields = QUALITY_FIELDS;
  miscFields = MISC_FIELDS;
  signatureFields = SIGNATURE_FIELDS;

  private nf = new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  private df = new Intl.DateTimeFormat('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
  });

  constructor(
    private api: ApiService,
    public dialogRef: MatDialogRef<AnnexureSnapshotViewerDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: AnnexureSnapshotViewerDialogData,
  ) {}

  ngOnInit(): void {
    this.api.get<AnnexureSnapshotDetail>(this.data.url).subscribe({
      next: (res) => {
        this.detail = res;
        this.ann = res?.snapshot?.annexure ?? null;
        this.parseDiaBreakup();
        this.loading = false;
      },
      error: (e) => {
        this.error = e?.error?.detail || e?.error?.message || 'Failed to load snapshot.';
        this.loading = false;
      },
    });
  }

  private parseDiaBreakup(): void {
    if (!this.ann) return;
    const raw = this.ann['diawiseBreakup'];
    if (!raw) return;
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
      const list = Array.isArray(parsed) ? parsed : [];
      const cleaned = list.filter(r => r && typeof r === 'object');
      this.diaBreakup = cleaned;
      const colSet = new Set<string>();
      for (const r of cleaned) for (const k of Object.keys(r)) colSet.add(k);
      this.diaBreakupCols = Array.from(colSet);
    } catch {
      this.diaBreakup = [];
      this.diaBreakupCols = [];
    }
  }

  display(ann: any, f: FieldDef): string {
    const v = ann?.[f.key];
    if (v == null || v === '') return '';
    if (f.date) {
      const d = new Date(v);
      return isNaN(d.getTime()) ? String(v) : this.df.format(d);
    }
    if (f.num) {
      const n = Number(v);
      return isFinite(n) ? this.nf.format(n) : String(v);
    }
    return String(v);
  }

  downloadJson(): void {
    if (!this.detail) return;
    const blob = new Blob([JSON.stringify(this.detail.snapshot, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `annexure-${this.data.title.replace(/[^\w-]+/g, '_')}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  printSnapshot(): void {
    window.print();
  }

  close(): void {
    this.dialogRef.close();
  }
}
