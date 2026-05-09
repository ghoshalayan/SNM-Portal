import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';

import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';

/**
 * Final Working Sheet (Stage-2 BOM) editor.
 *
 * The customer's PO can carry a different qty / cost mix than the
 * original quotation. This component renders ``QuotPOWorkingSheet``
 * lines bound to ``/quotations/{id}/purchase-order/working-sheet`` —
 * cloned from the quotation's Working Sheet on Convert, mutable while
 * the PO is in Draft, snapshotted on Submit & Mature.
 *
 * Scope (Phase 1.5 v1): read + edit qty + add / delete line. The full
 * column-picker / goal-seek experience from the Stage-1 grid is out
 * of scope here — a separate growth iteration would unify the two.
 */

interface PoLine {
  poWorkingSheetId: number;
  quotPOId: number;
  sourceQuotDtlId: number | null;
  itemName: string | null;
  itemGradeName: string | null;
  itemDia: string | null;
  itemLength: string | null;
  itemUnit: string | null;
  quantity: number | null;
  modeOfDispatch: string | null;
  totRate: number | null;
  totAmount: number | null;
  isActive: boolean;
}

@Component({
  selector: 'app-quotation-po-working-sheet',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatTableModule, MatButtonModule,
    MatIconModule, MatFormFieldModule, MatInputModule, MatSelectModule,
    MatTooltipModule, MatProgressSpinnerModule, MatDialogModule,
  ],
  template: `
    <div class="po-ws-wrap">
      <div class="po-ws-head">
        <div class="po-ws-head-text">
          <strong>Final Working Sheet</strong>
          <span class="po-ws-meta">
            What was actually ordered. Editable until Submit &amp; Mature.
          </span>
        </div>
        <span *ngIf="readOnly" class="po-ws-locked">
          <mat-icon class="po-ws-locked-ico">lock</mat-icon>
          Locked — PO is {{ poStatus || 'past Draft' }}
        </span>
      </div>

      @if (loading) {
        <div class="po-ws-spinner"><mat-spinner diameter="32"></mat-spinner></div>
      } @else if (!lines.length) {
        <div class="po-ws-empty">
          <mat-icon>list_alt</mat-icon>
          <p>No working-sheet lines yet.</p>
          <p class="hint">
            Lines are cloned from the quotation's Working Sheet on
            <strong>Convert</strong>. If you don't see any here, either
            the quotation had no line items or the clone hasn't run.
          </p>
        </div>
      } @else {
        <table mat-table [dataSource]="lines" class="po-ws-table">
          <!-- Item -->
          <ng-container matColumnDef="item">
            <th mat-header-cell *matHeaderCellDef>Item</th>
            <td mat-cell *matCellDef="let row">
              <div class="cell-main">{{ row.itemName || '—' }}</div>
              <div class="cell-sub">
                {{ [row.itemGradeName, row.itemDia, row.itemLength] | json }}
              </div>
            </td>
          </ng-container>

          <!-- Qty (inline editable) -->
          <ng-container matColumnDef="quantity">
            <th mat-header-cell *matHeaderCellDef class="num-head">Qty (MT)</th>
            <td mat-cell *matCellDef="let row" class="num-cell">
              @if (!readOnly) {
                <input matInput type="number" step="0.01"
                  class="qty-input"
                  [ngModel]="row.quantity"
                  (ngModelChange)="onQtyChange(row, $event)"
                  (blur)="saveQty(row)" />
              } @else {
                {{ row.quantity | number:'1.2-2' }}
              }
            </td>
          </ng-container>

          <!-- Mode of Dispatch -->
          <ng-container matColumnDef="modeOfDispatch">
            <th mat-header-cell *matHeaderCellDef>Mode</th>
            <td mat-cell *matCellDef="let row">{{ row.modeOfDispatch || '—' }}</td>
          </ng-container>

          <!-- Total Rate / Amount (read-only display) -->
          <ng-container matColumnDef="totRate">
            <th mat-header-cell *matHeaderCellDef class="num-head">Tot. Rs/MT</th>
            <td mat-cell *matCellDef="let row" class="num-cell">
              {{ row.totRate | number:'1.2-2' }}
            </td>
          </ng-container>
          <ng-container matColumnDef="totAmount">
            <th mat-header-cell *matHeaderCellDef class="num-head">EX/FOR Price</th>
            <td mat-cell *matCellDef="let row" class="num-cell">
              {{ row.totAmount | number:'1.2-2' }}
            </td>
          </ng-container>

          <!-- Actions -->
          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef class="actions-head"></th>
            <td mat-cell *matCellDef="let row" class="actions-cell">
              <button mat-icon-button
                *ngIf="!readOnly"
                (click)="deleteLine(row)"
                matTooltip="Soft-delete this line">
                <mat-icon>delete</mat-icon>
              </button>
            </td>
          </ng-container>

          <tr mat-header-row *matHeaderRowDef="cols"></tr>
          <tr mat-row *matRowDef="let row; columns: cols"></tr>
        </table>

        <p class="po-ws-foot-note">
          Cost-head adjustments (TPWGST, freight, OHD, etc.) at the PO level
          will arrive in a follow-up iteration — for now, qty changes here
          flow through to Viability + Annexure once the PO is Submitted.
        </p>
      }
    </div>
  `,
  styles: [`
    .po-ws-wrap { padding: 6px 0; }
    .po-ws-head {
      display: flex; align-items: center; justify-content: space-between;
      gap: 12px;
      padding: 8px 4px 14px;
      flex-wrap: wrap;
    }
    .po-ws-head-text strong {
      font-size: 15px;
      color: var(--snm-text-primary);
    }
    .po-ws-meta {
      display: block;
      font-size: 12px;
      color: var(--snm-text-muted);
      margin-top: 2px;
    }
    .po-ws-locked {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 4px 10px; border-radius: 14px;
      background: rgba(0,0,0,0.06);
      color: var(--snm-text-muted);
      font-size: 11px; font-weight: 600;
      letter-spacing: 0.3px; text-transform: uppercase;
    }
    .po-ws-locked-ico { font-size: 14px; width: 14px; height: 14px; }

    .po-ws-spinner { display: flex; justify-content: center; padding: 32px 0; }
    .po-ws-empty {
      text-align: center; padding: 40px 20px;
      color: var(--snm-text-muted);
    }
    .po-ws-empty mat-icon { font-size: 40px; width: 40px; height: 40px; opacity: 0.55; }
    .po-ws-empty .hint {
      font-size: 12px; max-width: 460px; margin: 6px auto 0;
      color: var(--snm-text-faint); line-height: 1.5;
    }

    .po-ws-table { width: 100%; }
    .num-head, .num-cell { text-align: right; }
    .actions-head, .actions-cell { width: 56px; text-align: center; }
    .cell-main { font-weight: 500; }
    .cell-sub { font-size: 11px; color: var(--snm-text-muted); }
    .qty-input {
      width: 90px;
      padding: 4px 6px;
      border: 1px solid var(--snm-border-field, rgba(0,0,0,0.2));
      border-radius: 4px;
      font-size: 13px;
      text-align: right;
      background: var(--snm-bg-card);
    }
    .qty-input:focus { outline: 2px solid var(--snm-accent); outline-offset: -1px; }

    .po-ws-foot-note {
      margin-top: 12px;
      font-size: 11px;
      color: var(--snm-text-faint);
      font-style: italic;
    }
  `],
})
export class QuotationPoWorkingSheetComponent implements OnChanges {
  @Input({ required: true }) quotId!: number;
  /** Drives the locked banner + disabled inline edits. The component
   *  refuses to mutate when this is true; the backend re-enforces. */
  @Input() readOnly = false;
  /** Surface the PO status string in the locked chip ("Submitted" /
   *  "Rejected"). Optional — falls back to "past Draft". */
  @Input() poStatus: string | null = null;

  /** Fires after a successful add / edit / delete so the parent can
   *  refresh totals or trigger a reload. */
  @Output() linesChanged = new EventEmitter<void>();

  cols = ['item', 'quantity', 'modeOfDispatch', 'totRate', 'totAmount', 'actions'];
  lines: PoLine[] = [];
  loading = false;

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    private dialog: MatDialog,
  ) {}

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['quotId'] && this.quotId) {
      this.load();
    }
  }

  private load(): void {
    this.loading = true;
    this.api.get<PoLine[]>(`/quotations/${this.quotId}/purchase-order/working-sheet`).subscribe({
      next: (rs) => {
        this.lines = rs || [];
        this.loading = false;
      },
      error: () => {
        this.lines = [];
        this.loading = false;
      },
    });
  }

  onQtyChange(row: PoLine, value: number | null): void {
    row.quantity = value ?? null;
  }

  /** Inline qty save on blur. The backend recomputes totRate /
   *  totAmount from cost heads; we just push the new qty and pull
   *  back the recomputed row. */
  saveQty(row: PoLine): void {
    if (this.readOnly) return;
    this.api.put<PoLine>(
      `/quotations/${this.quotId}/purchase-order/working-sheet/${row.poWorkingSheetId}`,
      { quantity: row.quantity },
    ).subscribe({
      next: (updated) => {
        Object.assign(row, updated);
        this.linesChanged.emit();
      },
      error: (err) => {
        this.notify.error(err?.error?.detail || 'Failed to save qty.');
        this.load();
      },
    });
  }

  deleteLine(row: PoLine): void {
    if (this.readOnly) return;
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Delete working-sheet line',
        message: `Remove "${row.itemName || 'this line'}" from the Final Working Sheet?`,
        confirmText: 'Delete',
        confirmColor: 'warn',
      },
    });
    ref.afterClosed().subscribe(ok => {
      if (!ok) return;
      this.api.delete(
        `/quotations/${this.quotId}/purchase-order/working-sheet/${row.poWorkingSheetId}`,
      ).subscribe({
        next: () => {
          this.lines = this.lines.filter(l => l.poWorkingSheetId !== row.poWorkingSheetId);
          this.linesChanged.emit();
          this.notify.success('Line deleted.');
        },
        error: (err) => this.notify.error(err?.error?.detail || 'Failed to delete.'),
      });
    });
  }

  /** Public refresh — invoked by parent when PO status changes
   *  (e.g. user just clicked Submit & Mature elsewhere). */
  refresh(): void { this.load(); }
}
