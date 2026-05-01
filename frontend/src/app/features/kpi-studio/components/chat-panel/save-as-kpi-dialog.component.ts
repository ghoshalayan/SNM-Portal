import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  Inject,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatChipsModule } from '@angular/material/chips';
import {
  MatDialogModule, MatDialogRef, MAT_DIALOG_DATA,
} from '@angular/material/dialog';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { KpiService } from '../../services/kpi.service';
import { DashboardService } from '../../services/dashboard.service';
import { NotificationService } from '../../../../core/services/notification.service';
import {
  CardSize,
  ChartConfig,
  ChartType,
  DashboardSummary,
  KpiCreateRequest,
} from '../../models/schema.types';

const CHART_TYPE_OPTIONS: { value: ChartType; label: string }[] = [
  { value: 'scorecard',  label: 'Score card' },
  { value: 'stat_group', label: 'Stat group' },
  { value: 'bar',        label: 'Bar' },
  { value: 'line',       label: 'Line' },
  { value: 'pie',        label: 'Pie' },
  { value: 'table',      label: 'Table' },
];

const CARD_SIZE_OPTIONS: { value: CardSize; label: string }[] = [
  { value: 'sm',   label: 'Small (1 col)' },
  { value: 'md',   label: 'Medium (2 cols)' },
  { value: 'lg',   label: 'Large (3 cols)' },
  { value: 'wide', label: 'Wide (4 cols)' },
];

export interface SaveAsKpiDialogData {
  sql: string;
  chart_config: ChartConfig | null;
  defaultName: string;
}

/** What the dialog returns to its caller — populated only on success. */
export interface SaveAsKpiResult {
  kpi_id: number;
  dashboard_id: number | null;
}

@Component({
  selector: 'app-save-as-kpi-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    MatButtonModule, MatIconModule, MatFormFieldModule, MatInputModule,
    MatSelectModule, MatSlideToggleModule, MatProgressBarModule,
    MatChipsModule, MatDialogModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="title-icon">bookmark_add</mat-icon>
      Save as KPI
    </h2>

    <mat-dialog-content>
      <p class="hint">
        Saves the agent's SQL + chart as a reusable KPI. Dashboards
        re-execute it live every render — they pick up new data
        automatically.
      </p>

      <mat-form-field appearance="outline" class="full">
        <mat-label>Name</mat-label>
        <input matInput maxlength="200"
               [ngModel]="name()" (ngModelChange)="name.set($event)"
               cdkFocusInitial required>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full">
        <mat-label>Description (optional)</mat-label>
        <textarea matInput rows="2" maxlength="1000"
                  [ngModel]="description()"
                  (ngModelChange)="description.set($event)"></textarea>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full">
        <mat-label>Chart type</mat-label>
        <mat-select [value]="chartType()" (valueChange)="chartType.set($event)">
          <mat-option *ngFor="let c of chartTypes" [value]="c.value">
            {{ c.label }}
          </mat-option>
        </mat-select>
        <mat-hint>Pre-filled from the agent's suggestion. Override if you prefer.</mat-hint>
      </mat-form-field>

      <details class="sql-disclosure">
        <summary>Show SQL ({{ data.sql.length }} chars)</summary>
        <pre class="sql-preview">{{ data.sql }}</pre>
      </details>

      <!-- Optional: drop the new KPI on a dashboard in one shot. -->
      <mat-slide-toggle
        class="add-to-dash"
        [checked]="addToDashboard()"
        (change)="addToDashboard.set($event.checked)">
        Add to a dashboard
      </mat-slide-toggle>

      <ng-container *ngIf="addToDashboard()">
        <mat-form-field appearance="outline" class="full">
          <mat-label>Dashboard</mat-label>
          <mat-select [value]="dashboardId()"
                      (valueChange)="dashboardId.set($event)"
                      [disabled]="dashboardsLoading()">
            <mat-option *ngFor="let d of dashboards()" [value]="d.dashboard_id">
              {{ d.name }} <span class="scope-pill">·{{ d.scope }}</span>
            </mat-option>
            <mat-option *ngIf="!dashboards().length && !dashboardsLoading()" [value]="null" disabled>
              No dashboards available — create one first.
            </mat-option>
          </mat-select>
          <mat-progress-bar *ngIf="dashboardsLoading()" mode="indeterminate"></mat-progress-bar>
        </mat-form-field>

        <mat-form-field appearance="outline" class="full">
          <mat-label>Card size</mat-label>
          <mat-select [value]="cardSize()" (valueChange)="cardSize.set($event)">
            <mat-option *ngFor="let s of cardSizes" [value]="s.value">
              {{ s.label }}
            </mat-option>
          </mat-select>
        </mat-form-field>
      </ng-container>

      <div *ngIf="error()" class="error-banner">
        <mat-icon>error_outline</mat-icon>
        <span>{{ error() }}</span>
      </div>

      <mat-progress-bar *ngIf="saving()" mode="indeterminate"></mat-progress-bar>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button [mat-dialog-close]="null" [disabled]="saving()">
        Cancel
      </button>
      <button mat-flat-button color="primary"
              [disabled]="!canSave()"
              (click)="save()">
        <mat-icon>save</mat-icon>
        {{ addToDashboard() ? 'Save & Add' : 'Save KPI' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    h2 mat-dialog-title { display: flex; align-items: center; gap: 8px; }
    .title-icon { color: var(--snm-accent, #4a90e2); }
    .full { width: 100%; }
    .hint {
      margin: 0 0 12px; color: var(--snm-text-muted); font-size: 0.85rem;
    }
    .sql-disclosure {
      margin: 4px 0 12px;
      summary { cursor: pointer; color: var(--snm-text-muted); font-size: 0.8rem; }
    }
    .sql-preview {
      margin: 8px 0 0; padding: 8px 10px;
      background: var(--snm-bg-panel, #f7f8fa);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 4px;
      font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
      font-size: 0.78rem; line-height: 1.4;
      max-height: 200px; overflow: auto;
      white-space: pre-wrap; word-break: break-word;
      color: var(--snm-text-secondary);
    }
    .add-to-dash { display: block; margin: 4px 0 12px; }
    .scope-pill {
      color: var(--snm-text-muted); font-size: 0.75rem; margin-left: 4px;
    }
    .error-banner {
      display: flex; gap: 8px; padding: 10px 12px;
      background: rgba(229, 57, 53, 0.08);
      border: 1px solid var(--snm-error, #e53935);
      color: var(--snm-error, #c62828);
      border-radius: 6px; font-size: 0.85rem; align-items: center;
      margin: 8px 0;
    }
  `],
})
export class SaveAsKpiDialogComponent implements OnInit {
  private readonly kpis = inject(KpiService);
  private readonly dashboardService = inject(DashboardService);
  private readonly notify = inject(NotificationService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly chartTypes = CHART_TYPE_OPTIONS;
  readonly cardSizes = CARD_SIZE_OPTIONS;

  // Form state
  readonly name = signal('');
  readonly description = signal('');
  readonly chartType = signal<ChartType>('table');
  readonly addToDashboard = signal(false);
  readonly dashboardId = signal<number | null>(null);
  readonly cardSize = signal<CardSize>('md');

  // Async state
  readonly dashboardsLoading = signal(false);
  readonly dashboards = signal<DashboardSummary[]>([]);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);

  readonly canSave = computed(() => {
    if (this.saving()) return false;
    if (!this.name().trim()) return false;
    if (this.addToDashboard() && this.dashboardId() == null) return false;
    return true;
  });

  constructor(
    private readonly ref: MatDialogRef<SaveAsKpiDialogComponent, SaveAsKpiResult | null>,
    @Inject(MAT_DIALOG_DATA) public data: SaveAsKpiDialogData,
  ) {
    this.name.set(data.defaultName || '');
    if (data.chart_config?.type) {
      this.chartType.set(data.chart_config.type);
    }
  }

  ngOnInit(): void {
    // Pre-fetch dashboards so the dropdown is populated by the time the
    // user toggles "Add to a dashboard". One round-trip per dialog open.
    this.dashboardsLoading.set(true);
    this.dashboardService.list()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.dashboards.set(res.items);
          this.dashboardsLoading.set(false);
        },
        error: () => {
          this.dashboardsLoading.set(false);
          this.dashboards.set([]);
        },
      });
  }

  save(): void {
    if (!this.canSave()) return;
    this.saving.set(true);
    this.error.set(null);

    const payload: KpiCreateRequest = {
      name: this.name().trim(),
      description: this.description().trim() || null,
      query_text: this.data.sql,
      chart_config: this.buildChartConfig(),
    };

    this.kpis.create(payload)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: kpi => {
          if (this.addToDashboard() && this.dashboardId() != null) {
            // Two-step: KPI created, now drop it on the dashboard.
            this.dashboardService.addItem(this.dashboardId()!, {
              kpi_id: kpi.kpi_id,
              size_class: this.cardSize(),
            }).subscribe({
              next: () => {
                this.saving.set(false);
                this.notify.success(`Saved "${kpi.name}" and added it to the dashboard.`);
                this.ref.close({
                  kpi_id: kpi.kpi_id,
                  dashboard_id: this.dashboardId(),
                });
                this.router.navigate(['/kpi-studio/dashboards', this.dashboardId()]);
              },
              error: err => {
                // The KPI was saved, but adding to the dashboard failed
                // — surface clearly so the user isn't surprised by a
                // "saved but not on dashboard" outcome.
                this.saving.set(false);
                this.error.set(
                  `KPI saved (id ${kpi.kpi_id}), but adding to the dashboard failed: ` +
                  (err?.error?.detail?.message ?? err?.error?.detail ?? err?.message ?? 'unknown'),
                );
              },
            });
          } else {
            this.saving.set(false);
            this.notify.success(`Saved "${kpi.name}".`);
            this.ref.close({ kpi_id: kpi.kpi_id, dashboard_id: null });
            this.router.navigate(['/kpi-studio/kpis', kpi.kpi_id]);
          }
        },
        error: err => {
          this.saving.set(false);
          this.error.set(
            err?.error?.detail?.message ?? err?.error?.detail ?? 'Save failed',
          );
        },
      });
  }

  private buildChartConfig(): ChartConfig {
    // Reuse the agent's suggested ``config`` payload (mapping of chart
    // axes etc.) when the user kept the same chart type. If they
    // overrode the type, drop the config — the renderer falls back to
    // sensible per-type defaults.
    const suggested = this.data.chart_config;
    const useSuggestion = !!suggested && suggested.type === this.chartType();
    return {
      type: this.chartType(),
      config: useSuggestion ? (suggested!.config || {}) : {},
      style: suggested?.style,
    };
  }
}
