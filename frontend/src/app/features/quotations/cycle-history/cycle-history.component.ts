import {
  Component, Input, OnChanges, OnInit, SimpleChanges,
} from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { CycleService, OrderCycleBundle } from '../services/cycle.service';
import { NotificationService } from '../../../core/services/notification.service';
import { environment } from '../../../../environments/environment';

/** Read-only timeline of every cycle on a quotation. Each cycle is
 *  one card: status badge, started/closed metadata, the cycle's
 *  POs/LOIs in a compact table, and lite refs to its WS/viability/
 *  annexure heads. Renders in the Stage-2 "Cycle History" tab.
 *
 *  Pure presentation — no actions. Mutations live in the per-cycle
 *  workspace (Stage 2 main panel) and the strip; this view is for
 *  renewal conversations with customers and audit-style scans. */
@Component({
  selector: 'app-cycle-history',
  standalone: true,
  imports: [
    CommonModule, DatePipe,
    MatButtonModule, MatIconModule, MatTooltipModule, MatProgressSpinnerModule,
  ],
  template: `
    <div class="cycle-history">
      <div *ngIf="loading" class="loading">
        <mat-spinner diameter="32"></mat-spinner>
        <span>Loading cycle history…</span>
      </div>

      <div *ngIf="!loading && bundles.length === 0" class="empty">
        <mat-icon>history</mat-icon>
        <p>No call-off cycles yet.</p>
        <p class="hint">
          Start the first cycle on the Purchase Order tab to begin
          tracking call-offs.
        </p>
      </div>

      <article *ngFor="let b of bundles" class="cycle-card"
               [class.status-active]="b.cycle.status === 'Active'"
               [class.status-complete]="b.cycle.status === 'Complete'"
               [class.status-abandoned]="b.cycle.status === 'Abandoned'">
        <header class="cycle-head">
          <div class="cycle-title">
            <mat-icon class="cycle-ico">{{ iconFor(b.cycle.status) }}</mat-icon>
            <h3>Cycle {{ b.cycle.cycleNo }}</h3>
            <span class="status-chip">{{ b.cycle.status }}</span>
          </div>
          <div class="cycle-meta">
            <span matTooltip="Started">
              <mat-icon>schedule</mat-icon>
              {{ b.cycle.startedOn | date:'mediumDate' }}
            </span>
            <span *ngIf="b.cycle.closedOn" matTooltip="Closed">
              <mat-icon>event_available</mat-icon>
              {{ b.cycle.closedOn | date:'mediumDate' }}
            </span>
            <span *ngIf="b.cycle.parentCycleId"
                  matTooltip="Inherited from this cycle">
              <mat-icon>link</mat-icon>
              from Cycle {{ parentCycleNo(b.cycle.parentCycleId) }}
            </span>
            <button mat-stroked-button color="primary" type="button"
                    class="export-btn"
                    [disabled]="exportingCycleId === b.cycle.quotOrderCycleId"
                    (click)="downloadExcel(b)"
                    matTooltip="Download this cycle as Excel (Summary + WS + Viability)">
              <mat-progress-spinner *ngIf="exportingCycleId === b.cycle.quotOrderCycleId"
                                    diameter="14" mode="indeterminate"></mat-progress-spinner>
              <mat-icon *ngIf="exportingCycleId !== b.cycle.quotOrderCycleId">download</mat-icon>
              Export Excel
            </button>
          </div>
        </header>

        <div class="cycle-body">
          <!-- POs / LOIs in this cycle -->
          <div class="po-block">
            <div class="block-label">
              POs &amp; LOIs ({{ b.purchaseOrders.length }})
            </div>
            <div *ngIf="b.purchaseOrders.length === 0" class="block-empty">
              No POs or LOIs captured in this cycle.
            </div>
            <table *ngIf="b.purchaseOrders.length > 0" class="po-table">
              <thead>
                <tr>
                  <th>Seq</th>
                  <th>Type</th>
                  <th>PO No</th>
                  <th>Date</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                <tr *ngFor="let p of b.purchaseOrders">
                  <td>{{ p.loiSequence ?? '—' }}</td>
                  <td>
                    <span class="kind-chip" [class.is-loi]="p.isLOI">
                      {{ p.isLOI ? 'LOI' : 'PO' }}
                    </span>
                  </td>
                  <td>{{ p.poNo }}</td>
                  <td>{{ p.poDate | date:'mediumDate' }}</td>
                  <td>{{ p.status }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Downstream artifacts (lite) -->
          <div class="downstream">
            <div class="ds-chip">
              <mat-icon>build_circle</mat-icon>
              FWS:
              <strong>{{ b.workingSheetLineCount }}</strong>
              line{{ b.workingSheetLineCount === 1 ? '' : 's' }}
            </div>
            <div class="ds-chip" [class.has-viab]="b.viabilityId != null">
              <mat-icon>query_stats</mat-icon>
              Viability:
              <strong>{{ b.viabilityStatus || '—' }}</strong>
            </div>
            <div class="ds-chip" [class.has-annx]="b.annexureId != null">
              <mat-icon>description</mat-icon>
              Annexure:
              <strong>{{ b.annexureStatus || '—' }}</strong>
            </div>
          </div>

          <div class="cycle-notes" *ngIf="b.cycle.notes">
            <mat-icon>sticky_note_2</mat-icon>
            <span>{{ b.cycle.notes }}</span>
          </div>
        </div>
      </article>
    </div>
  `,
  styles: [`
    .cycle-history { display: flex; flex-direction: column; gap: 12px; }
    .loading {
      display: flex; align-items: center; gap: 12px;
      padding: 40px; justify-content: center;
      color: var(--snm-text-secondary);
    }
    .empty {
      text-align: center; padding: 56px 24px;
      color: var(--snm-text-muted);
    }
    .empty mat-icon {
      font-size: 48px; width: 48px; height: 48px; opacity: 0.55;
      margin-bottom: 12px;
    }
    .empty p { margin: 4px 0; font-size: 14px; }
    .empty .hint {
      font-size: 12px; color: var(--snm-text-faint);
      max-width: 420px; margin: 6px auto 0;
    }

    .cycle-card {
      border: 1px solid var(--snm-border-divider);
      border-left: 4px solid var(--snm-accent);
      border-radius: 8px;
      background: var(--snm-bg-card);
      overflow: hidden;
    }
    .cycle-card.status-complete { border-left-color: #2e7d32; }
    .cycle-card.status-abandoned {
      border-left-color: var(--snm-text-faint);
      opacity: 0.78;
    }

    .cycle-head {
      display: flex; align-items: flex-start; justify-content: space-between;
      flex-wrap: wrap; gap: 12px;
      padding: 14px 18px; background: var(--snm-bg-header-row);
      border-bottom: 1px solid var(--snm-border-divider);
    }
    .cycle-title { display: flex; align-items: center; gap: 10px; }
    .cycle-title h3 { margin: 0; font-size: 16px; font-weight: 600; }
    .cycle-ico { color: var(--snm-accent); }
    .status-active .cycle-ico { color: var(--snm-accent); }
    .status-complete .cycle-ico { color: #2e7d32; }
    .status-abandoned .cycle-ico { color: var(--snm-text-faint); }
    .status-chip {
      padding: 2px 10px; border-radius: 10px;
      background: var(--snm-accent-shadow); color: var(--snm-accent);
      font-size: 11px; font-weight: 600; text-transform: uppercase;
    }
    .status-complete .status-chip { background: rgba(46,125,50,.14); color: #2e7d32; }
    .status-abandoned .status-chip {
      background: rgba(0,0,0,.10); color: var(--snm-text-faint);
    }

    .cycle-meta {
      display: flex; flex-wrap: wrap; gap: 14px;
      font-size: 12px; color: var(--snm-text-secondary);
    }
    .cycle-meta span {
      display: inline-flex; align-items: center; gap: 4px;
    }
    .cycle-meta mat-icon {
      font-size: 14px; width: 14px; height: 14px;
      color: var(--snm-text-muted);
    }
    .export-btn {
      margin-left: auto;
      font-size: 12px !important;
      line-height: 1.2 !important;
      min-width: 110px;
    }
    .export-btn mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .export-btn mat-progress-spinner { display: inline-block; margin-right: 6px; }

    .cycle-body { padding: 14px 18px; }
    .block-label {
      font-size: 12px; font-weight: 600;
      color: var(--snm-text-secondary); margin-bottom: 6px;
    }
    .block-empty {
      font-size: 12px; color: var(--snm-text-faint);
      font-style: italic; padding: 8px 0;
    }

    .po-table {
      width: 100%; border-collapse: collapse; font-size: 13px;
      margin-bottom: 12px;
    }
    .po-table th, .po-table td {
      padding: 6px 10px; text-align: left;
      border-bottom: 1px solid var(--snm-border-divider);
    }
    .po-table th {
      font-size: 11px; text-transform: uppercase;
      color: var(--snm-text-secondary); font-weight: 600;
    }
    .kind-chip {
      padding: 1px 8px; border-radius: 8px;
      background: rgba(25,118,210,.12); color: #1976d2;
      font-size: 11px; font-weight: 600;
    }
    .kind-chip.is-loi {
      background: rgba(245,124,0,.14); color: #f57c00;
    }

    .downstream {
      display: flex; flex-wrap: wrap; gap: 10px;
      margin-top: 4px;
    }
    .ds-chip {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 4px 10px; border-radius: 12px;
      background: var(--snm-bg-panel);
      border: 1px solid var(--snm-border-divider);
      font-size: 12px; color: var(--snm-text-secondary);
    }
    .ds-chip mat-icon {
      font-size: 14px; width: 14px; height: 14px;
      color: var(--snm-text-muted);
    }
    .ds-chip.has-viab, .ds-chip.has-annx { color: var(--snm-text-primary); }

    .cycle-notes {
      display: flex; align-items: flex-start; gap: 6px;
      margin-top: 12px;
      padding: 8px 10px;
      background: rgba(0,0,0,.03);
      border-left: 3px solid var(--snm-border-divider);
      font-size: 12px; color: var(--snm-text-secondary);
      white-space: pre-wrap;
    }
    .cycle-notes mat-icon {
      font-size: 16px; width: 16px; height: 16px;
      color: var(--snm-text-muted);
    }
  `],
})
export class CycleHistoryComponent implements OnInit, OnChanges {
  @Input({ required: true }) quotId!: number;

  bundles: OrderCycleBundle[] = [];
  loading = false;
  /** Cycle id whose Excel export is currently in flight — drives the
   *  per-row spinner on the Export button. */
  exportingCycleId: number | null = null;

  constructor(
    private cycleService: CycleService,
    private notifications: NotificationService,
    private http: HttpClient,
  ) {}

  ngOnInit(): void {
    if (this.quotId) this.load();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['quotId'] && !changes['quotId'].firstChange) {
      this.load();
    }
  }

  load(): void {
    if (!this.quotId) return;
    this.loading = true;
    this.cycleService.history(this.quotId).subscribe({
      next: (resp) => {
        this.bundles = resp.bundles;
        this.loading = false;
      },
      error: (e) => {
        this.notifications.error(
          e?.error?.message || e?.error?.detail || 'Failed to load cycle history.',
        );
        this.loading = false;
      },
    });
  }

  iconFor(status: string): string {
    switch (status) {
      case 'Active': return 'play_circle_outline';
      case 'Complete': return 'check_circle_outline';
      case 'Abandoned': return 'cancel';
      default: return 'help_outline';
    }
  }

  /** Resolve a parentCycleId to its cycleNo for the "from Cycle N"
   *  hint. Null when the parent isn't in the current list (shouldn't
   *  happen for active quotations but defensive). */
  parentCycleNo(parentId: number): number | string {
    const parent = this.bundles.find(b => b.cycle.quotOrderCycleId === parentId);
    return parent ? parent.cycle.cycleNo : '?';
  }

  /** Hit ``GET /quotations/{qid}/cycles/{cId}/export`` and trigger a
   *  download. Uses ``HttpClient`` directly (not ``ApiService``)
   *  because we need ``responseType: 'blob'`` + the Content-Disposition
   *  header to derive the filename — the same pattern as the existing
   *  viability download. */
  downloadExcel(b: OrderCycleBundle): void {
    const cycleId = b.cycle.quotOrderCycleId;
    this.exportingCycleId = cycleId;
    const url =
      `${environment.apiUrl}/quotations/${this.quotId}` +
      `/cycles/${cycleId}/export`;
    this.http.get(url, { responseType: 'blob', observe: 'response' }).subscribe({
      next: (resp) => {
        this.exportingCycleId = null;
        const blob = resp.body;
        if (!blob) {
          this.notifications.error('Empty Excel file.');
          return;
        }
        let filename = `Cycle-${b.cycle.cycleNo}-${this.quotId}.xlsx`;
        const cd =
          resp.headers.get('Content-Disposition') ||
          resp.headers.get('content-disposition');
        if (cd) {
          const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
          if (m && m[1]) filename = decodeURIComponent(m[1]);
        }
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
      },
      error: () => {
        this.exportingCycleId = null;
        this.notifications.error('Failed to download cycle Excel.');
      },
    });
  }
}
