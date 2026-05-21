import { ChangeDetectionStrategy, Component, Inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatRadioModule } from '@angular/material/radio';
import { MatIconModule } from '@angular/material/icon';
import { MatDividerModule } from '@angular/material/divider';
import { MatTooltipModule } from '@angular/material/tooltip';

/**
 * Confirmation modal for the CR #1 bulk-apply flow. Used in two places:
 *  - Viability Sheet: triggered on inline cell blur when the value changes
 *  - Final Working Sheet: triggered after the line-item dialog save when
 *    exactly one cost-head field changed
 *
 * The dialog has two stages of consent:
 *   1. Confirm the single change (always required to commit)
 *   2. Optionally propagate to other rows — either all of them, or a
 *      hand-picked subset via the checkbox list
 *
 * Caller is responsible for actually applying the change (this dialog
 * just collects intent). The `applyToRowIds` array in the result excludes
 * the source row by construction.
 */

export interface BulkApplyCandidateRow {
  /** Stable identifier (any type the caller uses for row keying). */
  id: number | string;
  /** Compact one-line label — typically "Item · Dia · Length · Qty". */
  label: string;
  /** Current value of the field being changed, for the checkbox-row hint. */
  currentValue: number | string | null;
}

export interface BulkApplyDialogData {
  /** Display name of the cost-head being changed (e.g. "Marketing"). */
  fieldLabel: string;
  /** Old → new value preview shown at the top of the modal. */
  oldValue: number | string | null;
  newValue: number | string | null;
  /** Compact label of the row that just got edited (shown in the preface). */
  sourceRowLabel: string;
  /** OTHER rows in the same table that are eligible for propagation. */
  candidateRows: BulkApplyCandidateRow[];
}

export interface BulkApplyDialogResult {
  /** False when the user clicked Cancel or closed the dialog — caller
   *  should REVERT the source row's value. */
  confirmed: boolean;
  /** IDs of rows that should receive the new value. Empty array means
   *  "only confirm the source row, don't propagate." */
  applyToRowIds: (number | string)[];
}

type Mode = 'none' | 'all' | 'selected';

@Component({
  selector: 'app-bulk-apply-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    MatDialogModule, MatButtonModule, MatCheckboxModule,
    MatRadioModule, MatIconModule, MatDividerModule, MatTooltipModule,
  ],
  template: `
    <h2 mat-dialog-title class="title-row">
      <mat-icon class="title-icon">tune</mat-icon>
      <span>Confirm <strong>{{ data.fieldLabel }}</strong> change</span>
    </h2>

    <mat-dialog-content class="content">
      <p class="preface">
        <span class="row-label">{{ data.sourceRowLabel }}</span>
        <span class="change">
          <strong>{{ data.fieldLabel }}:</strong>
          <span class="old">{{ formatVal(data.oldValue) }}</span>
          <mat-icon class="arrow">arrow_forward</mat-icon>
          <span class="new">{{ formatVal(data.newValue) }}</span>
        </span>
      </p>

      <mat-divider class="div"></mat-divider>

      <mat-checkbox [checked]="confirmChecked()"
                    (change)="confirmChecked.set($event.checked)"
                    color="primary"
                    class="confirm-check">
        <strong>Confirm the change</strong>
        <span class="micro">(required)</span>
      </mat-checkbox>

      <mat-checkbox [checked]="propagate()"
                    (change)="propagate.set($event.checked)"
                    color="primary"
                    class="propagate-check"
                    [disabled]="!data.candidateRows.length">
        Make the same change for other line items
        <span class="micro" *ngIf="!data.candidateRows.length">(no other rows)</span>
      </mat-checkbox>

      @if (propagate()) {
        <div class="prop-body">
          <mat-radio-group [value]="mode()" (change)="setMode($event.value)" class="mode-radios">
            <mat-radio-button value="all" color="primary">
              All line items <span class="count">({{ data.candidateRows.length }})</span>
            </mat-radio-button>
            <mat-radio-button value="selected" color="primary">
              Selected line items
            </mat-radio-button>
          </mat-radio-group>

          @if (mode() === 'selected') {
            <div class="rows-list">
              <div class="rows-toolbar">
                <button mat-stroked-button type="button" (click)="selectAll()">
                  <mat-icon>select_all</mat-icon> Select all
                </button>
                <button mat-stroked-button type="button" (click)="clearSelection()">
                  <mat-icon>deselect</mat-icon> Clear
                </button>
                <span class="count-pill">{{ selectedCount() }} selected</span>
              </div>
              <div class="rows-grid">
                @for (row of data.candidateRows; track row.id) {
                  <mat-checkbox [checked]="selectedIds().has(row.id)"
                                (change)="toggleRow(row.id, $event.checked)"
                                color="primary"
                                class="row-check">
                    <span class="row-main">{{ row.label }}</span>
                    <span class="row-current">
                      now: <strong>{{ formatVal(row.currentValue) }}</strong>
                    </span>
                  </mat-checkbox>
                }
              </div>
            </div>
          }
        </div>
      }
    </mat-dialog-content>

    <mat-dialog-actions align="end" class="actions">
      <button mat-stroked-button (click)="cancel()">Cancel</button>
      <button mat-flat-button color="primary"
              (click)="apply()"
              [disabled]="!canApply()">
        <mat-icon>check</mat-icon> Apply
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host { display: block; }
    .title-row {
      display: flex; align-items: center; gap: 8px;
      margin: 0 !important;
    }
    .title-icon { color: var(--snm-accent); }
    .content { min-width: 520px; max-width: 720px; }
    .preface {
      margin: 0 0 12px;
      padding: 10px 12px;
      background: var(--snm-bg-panel);
      border-left: 3px solid var(--snm-accent);
      border-radius: 4px;
      display: flex; flex-direction: column; gap: 6px;
      font-size: 13px;
      color: var(--snm-text-primary);
    }
    .row-label { color: var(--snm-text-secondary); font-size: 12px; }
    .change { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .old {
      text-decoration: line-through;
      color: var(--snm-text-muted);
      padding: 1px 6px;
      background: rgba(0,0,0,0.04);
      border-radius: 3px;
    }
    .new {
      color: var(--snm-accent-dark, var(--snm-accent));
      font-weight: 700;
      padding: 1px 6px;
      background: var(--snm-accent-subtle, rgba(74, 144, 226, 0.10));
      border-radius: 3px;
    }
    .arrow { font-size: 16px; width: 16px; height: 16px; color: var(--snm-text-muted); }
    .div { margin: 4px 0 12px; }
    .confirm-check, .propagate-check {
      display: block;
      margin-bottom: 8px;
    }
    .confirm-check ::ng-deep .mdc-form-field { font-size: 14px; }
    .propagate-check ::ng-deep .mdc-form-field { font-size: 14px; }
    .micro {
      font-size: 11px;
      color: var(--snm-text-muted);
      margin-left: 6px;
      font-weight: 400;
    }
    .prop-body {
      margin: 4px 0 0 30px;
      padding: 10px 12px;
      border: 1px solid var(--snm-border-divider);
      border-radius: 4px;
      background: var(--snm-bg-card);
    }
    .mode-radios {
      display: flex; flex-direction: column; gap: 4px;
      margin-bottom: 10px;
    }
    .mode-radios mat-radio-button { display: block; }
    .count { color: var(--snm-text-muted); font-size: 12px; }
    .rows-list {
      border-top: 1px solid var(--snm-border-divider);
      padding-top: 8px;
    }
    .rows-toolbar {
      display: flex; align-items: center; gap: 8px;
      margin-bottom: 8px;
    }
    .rows-toolbar button { font-size: 12px; min-width: 0; }
    .count-pill {
      margin-left: auto;
      font-size: 12px; color: var(--snm-text-secondary);
      padding: 2px 8px;
      background: var(--snm-bg-panel);
      border-radius: 10px;
    }
    .rows-grid {
      max-height: 240px;
      overflow-y: auto;
      display: flex; flex-direction: column; gap: 2px;
    }
    .row-check { display: block; }
    .row-check ::ng-deep .mdc-form-field { width: 100%; }
    .row-main { font-size: 13px; }
    .row-current {
      font-size: 11px; color: var(--snm-text-muted);
      margin-left: 8px;
    }
    .actions { padding: 8px 16px 12px; }
  `],
})
export class BulkApplyDialogComponent {
  readonly confirmChecked = signal(true);  // Pre-ticked — the "OK" is the dominant intent.
  readonly propagate = signal(false);
  readonly mode = signal<Mode>('all');
  readonly selectedIds = signal(new Set<number | string>());

  readonly selectedCount = computed(() => this.selectedIds().size);

  readonly canApply = computed(() => {
    if (!this.confirmChecked()) return false;
    if (this.propagate() && this.mode() === 'selected' && this.selectedCount() === 0) {
      return false;
    }
    return true;
  });

  constructor(
    private dialogRef: MatDialogRef<BulkApplyDialogComponent, BulkApplyDialogResult>,
    @Inject(MAT_DIALOG_DATA) public data: BulkApplyDialogData,
  ) {}

  setMode(value: Mode): void {
    this.mode.set(value);
  }

  toggleRow(id: number | string, checked: boolean): void {
    const next = new Set(this.selectedIds());
    if (checked) next.add(id); else next.delete(id);
    this.selectedIds.set(next);
  }

  selectAll(): void {
    this.selectedIds.set(new Set(this.data.candidateRows.map(r => r.id)));
  }

  clearSelection(): void {
    this.selectedIds.set(new Set());
  }

  formatVal(v: number | string | null | undefined): string {
    if (v == null || v === '') return '—';
    if (typeof v === 'number') {
      return v.toLocaleString('en-IN', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
      });
    }
    return String(v);
  }

  cancel(): void {
    this.dialogRef.close({ confirmed: false, applyToRowIds: [] });
  }

  apply(): void {
    if (!this.canApply()) return;
    let ids: (number | string)[] = [];
    if (this.propagate()) {
      ids = this.mode() === 'all'
        ? this.data.candidateRows.map(r => r.id)
        : Array.from(this.selectedIds());
    }
    this.dialogRef.close({ confirmed: true, applyToRowIds: ids });
  }
}
