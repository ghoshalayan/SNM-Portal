import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  output,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';

import {
  TIME_PERIODS,
  TimePeriod,
  TimePeriodSelection,
} from '../../models/schema.types';

@Component({
  selector: 'app-period-selector',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    MatButtonModule, MatIconModule, MatChipsModule,
    MatFormFieldModule, MatInputModule, MatSelectModule, MatTooltipModule,
    MatDatepickerModule, MatNativeDateModule,
  ],
  template: `
    <div class="period-selector" [class.compact]="compact()">
      <!-- Compact mode (KPI editor) — single dropdown with tooltips
           on each option. The Custom-range date pickers (when used)
           render on a separate row below so the main control row
           stays single-line. -->
      <ng-container *ngIf="compact(); else chipMode">
        <mat-form-field appearance="outline" class="period-select">
          <mat-label>Period</mat-label>
          <mat-select [value]="value()" (valueChange)="setPeriod($event)">
            <mat-option *ngIf="allowAllTime()" [value]="null"
                        matTooltip="No time filter — every row counts">
              All time
            </mat-option>
            <mat-option *ngFor="let p of periods" [value]="p.value"
                        [matTooltip]="periodHint(p.value)">
              {{ p.label }}
            </mat-option>
          </mat-select>
        </mat-form-field>

        <div class="custom-row" *ngIf="value() === 'custom'">
          <mat-form-field appearance="outline" class="date-field">
            <mat-label>Start</mat-label>
            <input matInput [matDatepicker]="startPickerC"
                   [ngModel]="customStart()"
                   (ngModelChange)="customStart.set($event); emitCustom();">
            <mat-datepicker-toggle matIconSuffix [for]="startPickerC"></mat-datepicker-toggle>
            <mat-datepicker #startPickerC></mat-datepicker>
          </mat-form-field>
          <mat-form-field appearance="outline" class="date-field">
            <mat-label>End</mat-label>
            <input matInput [matDatepicker]="endPickerC"
                   [ngModel]="customEnd()"
                   (ngModelChange)="customEnd.set($event); emitCustom();">
            <mat-datepicker-toggle matIconSuffix [for]="endPickerC"></mat-datepicker-toggle>
            <mat-datepicker #endPickerC></mat-datepicker>
          </mat-form-field>
          <span *ngIf="customInvalid()" class="warn">
            <mat-icon>info</mat-icon>
            Pick start and end dates.
          </span>
        </div>
      </ng-container>

      <!-- Chip mode (default — dashboard surface where space is plentiful) -->
      <ng-template #chipMode>
        <mat-icon class="time-icon">schedule</mat-icon>
        <span class="label">Period:</span>
        <mat-chip-set>
          <mat-chip *ngIf="allowAllTime()"
                    [highlighted]="value() === null"
                    (click)="setPeriod(null)">
            All time
          </mat-chip>
          <mat-chip *ngFor="let p of periods"
                    [highlighted]="value() === p.value"
                    (click)="setPeriod(p.value)">
            {{ p.label }}
          </mat-chip>
        </mat-chip-set>

        <ng-container *ngIf="value() === 'custom'">
          <mat-form-field appearance="outline" class="date-field">
            <mat-label>Start</mat-label>
            <input matInput [matDatepicker]="startPicker"
                   [ngModel]="customStart()"
                   (ngModelChange)="customStart.set($event); emitCustom();">
            <mat-datepicker-toggle matIconSuffix [for]="startPicker"></mat-datepicker-toggle>
            <mat-datepicker #startPicker></mat-datepicker>
          </mat-form-field>
          <mat-form-field appearance="outline" class="date-field">
            <mat-label>End</mat-label>
            <input matInput [matDatepicker]="endPicker"
                   [ngModel]="customEnd()"
                   (ngModelChange)="customEnd.set($event); emitCustom();">
            <mat-datepicker-toggle matIconSuffix [for]="endPicker"></mat-datepicker-toggle>
            <mat-datepicker #endPicker></mat-datepicker>
          </mat-form-field>
          <span *ngIf="customInvalid()" class="warn">
            <mat-icon>info</mat-icon>
            Pick start and end dates.
          </span>
        </ng-container>
      </ng-template>
    </div>
  `,
  styles: [`
    .period-selector {
      display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
      padding: 8px 12px;
      background: var(--snm-bg-card, #fff);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 8px;
    }
    .period-selector.compact {
      padding: 0;
      background: transparent;
      border: none;
      flex-wrap: wrap; /* main control + Custom-range row stack vertically */
      gap: 8px;
    }
    .period-select { width: 140px; }
    .period-select ::ng-deep .mat-mdc-form-field-subscript-wrapper {
      display: none; /* no hint row in compact mode — saves a row */
    }
    .custom-row {
      display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
      flex: 1 1 100%; /* always its own row in compact mode */
    }
    .custom-row .date-field { width: 150px; }
    .time-icon {
      color: var(--snm-accent, #4a90e2);
      font-size: 20px; width: 20px; height: 20px;
    }
    .label {
      font-size: 0.85rem; font-weight: 500;
      color: var(--snm-text-secondary);
    }
    mat-chip-set {
      display: flex; flex-wrap: wrap; gap: 4px;
    }
    mat-chip { cursor: pointer; }
    .date-field { width: 160px; }
    .warn {
      display: flex; align-items: center; gap: 4px;
      font-size: 0.75rem; color: var(--snm-text-muted); font-style: italic;
      mat-icon { font-size: 14px; width: 14px; height: 14px; }
    }
  `],
})
export class PeriodSelectorComponent {
  readonly periods = TIME_PERIODS;

  /** Currently-selected period; ``null`` means "all time". */
  readonly value = input<TimePeriod | null>(null);
  /** Show the "All time" chip. Disable when the host wants to force a
   * filter (e.g. KPI editor with a time-bound query). */
  readonly allowAllTime = input(true);
  /** Compact mode renders a single dropdown instead of the full chip
   * row — used in the KPI editor where vertical real estate is at a
   * premium. Each option still surfaces its meaning via tooltip. */
  readonly compact = input(false);

  periodHint(p: TimePeriod): string {
    switch (p) {
      case 'daily':        return 'Last 24 hours';
      case 'weekly':       return 'Last 7 days';
      case 'monthly':      return 'Last 30 days';
      case 'quarterly':    return 'Last 90 days';
      case 'yearly':       return 'Last 365 days';
      case 'last_5_years': return 'Last 5 years (~1825 days)';
      case 'custom':       return 'Pick a specific start and end date';
      default:             return '';
    }
  }
  /** Initial custom range (when the host wants to remember it). */
  readonly initialStart = input<Date | null>(null);
  readonly initialEnd = input<Date | null>(null);

  /** Emits whenever the user picks a different period or adjusts the
   * custom date range. The parent decides when to act on it. */
  readonly periodChange = output<TimePeriodSelection>();

  // Custom date range — only meaningful when value() === 'custom'.
  readonly customStart = signal<Date | null>(null);
  readonly customEnd = signal<Date | null>(null);

  readonly customInvalid = computed(
    () => this.value() === 'custom'
      && (this.customStart() == null || this.customEnd() == null),
  );

  setPeriod(p: TimePeriod | null): void {
    if (p === 'custom') {
      // Switching INTO custom — only emit once dates are picked.
      this.periodChange.emit({
        period: 'custom',
        start_date: this.customStart()?.toISOString() ?? null,
        end_date: this.customEnd()?.toISOString() ?? null,
      });
      return;
    }
    this.periodChange.emit({ period: p });
  }

  emitCustom(): void {
    if (this.value() !== 'custom') return;
    if (this.customStart() == null || this.customEnd() == null) return;
    this.periodChange.emit({
      period: 'custom',
      start_date: this.customStart()!.toISOString(),
      end_date: this.customEnd()!.toISOString(),
    });
  }
}
