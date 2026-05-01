import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';

export const ADJUSTABLE_HEADS: string[] = [
  'Marketing', 'FreightTrailer', 'FreightTruck', 'Unloading', 'OHD', 'IFC',
  'WeighmentDiff', 'CD', 'SWECharge', 'CRS', 'IncCharge', 'ShortLnthCharge',
  'SpeciFicLnthCharge', 'ExtraCharge', 'Fluctuation', 'Commission', 'Misc',
  'Testing', 'MOUTOD', 'SplDisc', 'JC',
];

export const HEAD_LABEL: Record<string, string> = {
  Marketing: 'Marketing',
  FreightTrailer: 'Freight Trailer',
  FreightTruck: 'Freight Truck',
  Unloading: 'Unloading',
  OHD: 'OHD',
  IFC: 'IFC',
  WeighmentDiff: 'Weighment Diff.',
  CD: 'CD',
  SWECharge: 'S&E Charges',
  CRS: 'CRS',
  IncCharge: 'Incidental',
  ShortLnthCharge: 'Short Length',
  SpeciFicLnthCharge: 'Specific Length',
  ExtraCharge: 'Extra',
  Fluctuation: 'Fluctuation',
  Commission: 'Commission',
  Misc: 'Misc.',
  Testing: 'Testing',
  MOUTOD: 'MOU TOD',
  SplDisc: 'Special Discount',
  JC: 'JC',
};

export interface GoalSeekDialogData {
  /** The current viability line — we need all cost head values + itemName for the heading */
  line: any;
  /** Starting target (defaults to current totRate) */
  initialTarget?: number;
}

export interface GoalSeekDialogResult {
  target: number;
  adjustableHeads: string[];
}

@Component({
  selector: 'app-goal-seek-dialog',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatDialogModule, MatButtonModule, MatIconModule,
    MatCheckboxModule, MatFormFieldModule, MatInputModule, MatTableModule,
    MatTooltipModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="gs-title-icon">track_changes</mat-icon>
      Goal Seek — {{ data.line?.itemName || 'Line' }}
    </h2>

    <mat-dialog-content>
      <div class="gs-meta">
        <span><strong>Current Total (Rs/MT):</strong> {{ currentTotRate | number:'1.2-2' }}</span>
        <span><strong>Delta:</strong>
          <span [class.gs-delta-pos]="delta > 0" [class.gs-delta-neg]="delta < 0">
            {{ delta > 0 ? '+' : '' }}{{ delta | number:'1.2-2' }}
          </span>
        </span>
      </div>

      <mat-form-field appearance="outline" class="gs-target">
        <mat-label>Target Total (Rs/MT)</mat-label>
        <input matInput type="number" [(ngModel)]="target" step="0.01" />
      </mat-form-field>

      <div class="gs-heads-header">
        <span>Select heads that can absorb the delta:</span>
        <span class="gs-actions">
          <button mat-button type="button" (click)="selectAll()">All</button>
          <button mat-button type="button" (click)="selectNone()">None</button>
        </span>
      </div>

      <div class="gs-heads-grid">
        @for (h of heads; track h) {
          <mat-checkbox [(ngModel)]="selected[h]" class="gs-head-cb">
            <span class="gs-head-label">{{ labelOf(h) }}</span>
            <span class="gs-head-val" [class.gs-neg]="valueOf(h) < 0">
              {{ valueOf(h) | number:'1.2-2' }}
            </span>
          </mat-checkbox>
        }
      </div>

      @if (selectedCount === 0) {
        <div class="gs-warn">Select at least one head to run goal-seek.</div>
      }
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-raised-button color="primary"
        [disabled]="selectedCount === 0 || target == null"
        (click)="apply()">
        <mat-icon>play_arrow</mat-icon> Apply Goal Seek
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host { display: block; min-width: 520px; }
    h2 { display: flex; align-items: center; gap: 8px; margin: 0 0 4px; }
    .gs-title-icon { color: var(--snm-accent-dark, #3a6bb5); }
    .gs-meta {
      display: flex; gap: 16px; font-size: 13px;
      padding: 8px 0 12px;
      color: var(--snm-text-secondary);
    }
    .gs-delta-pos { color: #2e7d32; font-weight: 600; }
    .gs-delta-neg { color: #c62828; font-weight: 600; }
    .gs-target { width: 100%; margin-bottom: 8px; }

    .gs-heads-header {
      display: flex; justify-content: space-between; align-items: center;
      margin: 6px 0;
      font-size: 12px;
      color: var(--snm-text-secondary);
    }
    .gs-actions button { min-width: 0; padding: 0 8px; font-size: 12px; }

    .gs-heads-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 4px 16px;
      max-height: 320px;
      overflow-y: auto;
      padding: 4px;
      border: 1px solid var(--snm-border-divider);
      border-radius: 8px;
    }
    .gs-head-cb { width: 100%; }
    .gs-head-label { display: inline-block; min-width: 120px; }
    .gs-head-val { font-variant-numeric: tabular-nums; color: var(--snm-text-muted); }
    .gs-neg { color: #ef5350; }
    .gs-warn { color: #e65100; font-size: 12px; margin-top: 6px; }
  `],
})
export class GoalSeekDialogComponent {
  heads = ADJUSTABLE_HEADS;
  selected: Record<string, boolean> = {};
  target: number | null = null;

  constructor(
    public dialogRef: MatDialogRef<GoalSeekDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: GoalSeekDialogData,
  ) {
    const init = data?.initialTarget ?? Number(data?.line?.totRate ?? 0);
    this.target = isFinite(init) ? init : null;
  }

  labelOf(h: string): string { return HEAD_LABEL[h] || h; }

  valueOf(h: string): number {
    const v = this.data?.line?.[h];
    return v == null ? 0 : Number(v);
  }

  get currentTotRate(): number {
    return Number(this.data?.line?.totRate ?? 0);
  }

  get delta(): number {
    if (this.target == null) return 0;
    return Number(this.target) - this.currentTotRate;
  }

  get selectedCount(): number {
    return Object.values(this.selected).filter(Boolean).length;
  }

  selectAll(): void {
    this.heads.forEach(h => this.selected[h] = true);
  }

  selectNone(): void {
    this.selected = {};
  }

  apply(): void {
    if (this.target == null || this.selectedCount === 0) return;
    const chosen = this.heads.filter(h => this.selected[h]);
    const result: GoalSeekDialogResult = {
      target: Number(this.target),
      adjustableHeads: chosen,
    };
    this.dialogRef.close(result);
  }
}
