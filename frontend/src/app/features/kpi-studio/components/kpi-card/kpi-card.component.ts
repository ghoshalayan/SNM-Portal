import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { KpiService } from '../../services/kpi.service';
import {
  CARD_SIZES,
  CARD_SIZE_LABELS,
  CardSize,
  DashboardItem,
  ExecutionResult,
  TimePeriodSelection,
} from '../../models/schema.types';
import { ChartRendererComponent } from '../chart-renderer/chart-renderer.component';

@Component({
  selector: 'app-kpi-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatButtonModule, MatIconModule, MatMenuModule, MatTooltipModule,
    MatProgressSpinnerModule, MatChipsModule, MatDividerModule,
    ChartRendererComponent,
  ],
  template: `
    <article class="kpi-card"
             [class.editable]="editable()"
             [class.deleted]="!item().kpi_is_active"
             [attr.data-anim-in]="item().animation_in || null"
             [attr.data-anim-out]="item().animation_out || null">
      <header class="card-head">
        <div class="title-block">
          <h3 [matTooltip]="item().kpi_name">
            <mat-icon *ngIf="item().icon" class="title-icon" [attr.aria-hidden]="true">
              {{ item().icon }}
            </mat-icon>
            {{ item().title_override || item().kpi_name }}
          </h3>
          <div *ngIf="filterChips().length" class="filter-chips" matTooltip="Per-card filters applied to this KPI">
            <mat-chip *ngFor="let chip of filterChips()" disabled class="filter-chip">
              <mat-icon class="chip-icon">filter_alt</mat-icon>
              {{ chip }}
            </mat-chip>
          </div>
        </div>

        <div class="head-actions">
          <!-- Resize arrows — shrink + grow through the size lattice
               (sm → md → lg → wide). Visible on the unified dashboard
               and any host that opts in via [showResize]="true". -->
          <ng-container *ngIf="showResize()">
            <button mat-icon-button matTooltip="Smaller"
                    (click)="stepSize(-1)"
                    [disabled]="!canShrink()">
              <mat-icon>chevron_left</mat-icon>
            </button>
            <button mat-icon-button matTooltip="Larger"
                    (click)="stepSize(1)"
                    [disabled]="!canGrow()">
              <mat-icon>chevron_right</mat-icon>
            </button>
          </ng-container>
          <button mat-icon-button matTooltip="Refresh" (click)="reload()" [disabled]="loading()">
            <mat-icon>refresh</mat-icon>
          </button>
          <ng-container *ngIf="editable()">
            <button mat-icon-button [matMenuTriggerFor]="menu" matTooltip="Card options">
              <mat-icon>more_vert</mat-icon>
            </button>
            <mat-menu #menu="matMenu">
              <button mat-menu-item *ngFor="let s of sizes"
                      [disabled]="s === item().size_class"
                      (click)="resize.emit(s)">
                <mat-icon *ngIf="s === item().size_class">check</mat-icon>
                <span>{{ sizeLabel(s) }}</span>
              </button>
              <mat-divider></mat-divider>
              <button mat-menu-item (click)="remove.emit()">
                <mat-icon color="warn">delete</mat-icon>
                <span>Remove from dashboard</span>
              </button>
            </mat-menu>
          </ng-container>
        </div>
      </header>

      <section class="card-body">
        <!-- Skeleton shimmer — renders only on the *first* load when
             there's no result yet. Subsequent refreshes keep the old
             chart visible behind a subtle pulse so the user always
             has something to look at (perceived perf bump). -->
        <div *ngIf="loading() && !result()" class="skeleton">
          <span class="skel-bar w-60"></span>
          <span class="skel-bar w-90"></span>
          <span class="skel-bar w-40"></span>
          <span class="skel-bar w-75"></span>
        </div>
        <div *ngIf="loading() && result()" class="refresh-pulse"></div>

        <div *ngIf="!loading() && error()" class="error">
          <mat-icon>error_outline</mat-icon>
          <span>{{ error() }}</span>
          <button mat-button (click)="reload()">Retry</button>
        </div>

        <div *ngIf="!loading() && !error() && !item().kpi_is_active" class="error">
          <mat-icon>delete_outline</mat-icon>
          <span>Underlying KPI was deleted.</span>
        </div>

        <app-kpi-chart-renderer
          *ngIf="!loading() && !error() && item().kpi_is_active && result()"
          [result]="result()"
          [chartConfig]="effectiveChartConfig()" />
      </section>
    </article>
  `,
  styles: [`
    :host {
      display: block; height: 100%; width: 100%;
      animation: kpi-card-enter 360ms cubic-bezier(0.2, 0, 0, 1) both;
    }
    @keyframes kpi-card-enter {
      from { opacity: 0; transform: translateY(8px) scale(0.985); }
      to   { opacity: 1; transform: none; }
    }

    /* Phase J.2 — per-card animation overrides set by AI Polish.
       The article tag carries data-anim-in / data-anim-out so the
       host's :host enter animation stays as the global default,
       and these only fire when the user picks an override. */
    .kpi-card[data-anim-in="fade"]  { animation: kpi-anim-in-fade  420ms ease-out both; }
    .kpi-card[data-anim-in="slide"] { animation: kpi-anim-in-slide 420ms cubic-bezier(0.2, 0, 0, 1) both; }
    .kpi-card[data-anim-in="scale"] { animation: kpi-anim-in-scale 360ms cubic-bezier(0.2, 0, 0, 1) both; }
    .kpi-card[data-anim-in="none"]  { animation: none; }
    @keyframes kpi-anim-in-fade  { from { opacity: 0; } to { opacity: 1; } }
    @keyframes kpi-anim-in-slide { from { opacity: 0; transform: translateX(-24px); } to { opacity: 1; transform: none; } }
    @keyframes kpi-anim-in-scale { from { opacity: 0; transform: scale(0.92); } to { opacity: 1; transform: none; } }

    .title-icon {
      vertical-align: middle;
      font-size: 17px; width: 17px; height: 17px;
      margin-right: 4px;
      color: var(--snm-accent, #4a90e2);
    }
    .filter-chips {
      display: flex; flex-wrap: wrap; gap: 4px;
      margin-top: 2px;
    }
    .filter-chip {
      font-size: 0.65rem !important;
      min-height: 20px !important;
      padding: 0 8px !important;
      background: var(--snm-accent-subtle, rgba(91, 143, 217, 0.10)) !important;
      color: var(--snm-accent, #4a90e2) !important;
    }
    .filter-chip .chip-icon {
      font-size: 12px; width: 12px; height: 12px; margin-right: 2px;
    }
    .kpi-card {
      position: relative;
      display: flex; flex-direction: column; gap: 10px;
      height: 100%; padding: 14px 18px;
      /* Match the portal's standard card (welcome strip, period
         selector etc.). The earlier glass-bg-medium + heavy blur
         picked up the gradient blobs behind and washed out into a
         flat grey; this token + light divider keeps the card a clean
         dark navy in the dark theme and translucent white in light. */
      background: var(--snm-bg-card, rgba(255, 255, 255, 0.45));
      border: 1px solid var(--snm-border-divider, rgba(26, 58, 92, 0.1));
      border-radius: 12px;
      transition:
        border-color 200ms cubic-bezier(0.2, 0, 0, 1),
        box-shadow 240ms cubic-bezier(0.2, 0, 0, 1),
        transform 240ms cubic-bezier(0.2, 0, 0, 1),
        background 240ms cubic-bezier(0.2, 0, 0, 1);
    }
    .kpi-card:hover {
      border-color: var(--snm-accent-shadow, rgba(91, 143, 217, 0.4));
      box-shadow: 0 8px 24px var(--snm-glass-shadow-light, rgba(0, 0, 0, 0.06));
      transform: translateY(-2px);
    }
    .kpi-card.editable { cursor: grab; }
    .kpi-card.deleted { opacity: 0.6; }

    .card-head {
      position: relative; z-index: 1;
      display: flex; justify-content: space-between; align-items: center;
      gap: 8px; min-height: 32px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--snm-border-divider, rgba(0, 0, 0, 0.06));
    }
    .title-block { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
    .title-block h3 {
      margin: 0;
      font-size: 0.92rem; font-weight: 600;
      color: var(--snm-text-primary);
      letter-spacing: 0.01em;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .head-actions { display: flex; align-items: center; gap: 2px; flex-shrink: 0; }
    .head-actions button[mat-icon-button] {
      width: 30px; height: 30px; line-height: 30px;
      color: var(--snm-text-muted);
      transition: color 160ms ease, background 160ms ease;
      mat-icon { font-size: 17px; width: 17px; height: 17px; }
      &:hover {
        color: var(--snm-accent, #4a90e2);
        background: var(--snm-accent-subtle, rgba(91, 143, 217, 0.08));
      }
    }

    .card-body {
      position: relative; z-index: 1;
      flex: 1; min-height: 0;
      /* Stretching column — the chart-renderer inside fills the card
         body via height: 100% on its host. The previous place-items
         center left a tall card half-empty when its chart was small;
         charts now expand to use the height the user dragged. */
      display: flex;
      flex-direction: column;
      overflow: hidden;
      /* Custom scrollbar so any internal scroll doesn't break the glass. */
      scrollbar-width: thin;
      scrollbar-color: var(--snm-scrollbar-thumb, rgba(100, 140, 200, 0.2)) transparent;
    }
    .card-body app-kpi-chart-renderer {
      flex: 1 1 auto;
      min-height: 0;
      width: 100%;
    }
    .card-body::-webkit-scrollbar { width: 6px; height: 6px; }
    .card-body::-webkit-scrollbar-thumb {
      background: var(--snm-scrollbar-thumb, rgba(100, 140, 200, 0.2));
      border-radius: 3px;
    }
    .card-body::-webkit-scrollbar-thumb:hover {
      background: var(--snm-scrollbar-thumb-hover, rgba(100, 140, 200, 0.35));
    }
    .loading { display: flex; align-items: center; justify-content: center; }

    /* First-load skeleton — shimmering placeholder bars stand in for
       the chart while the executor runs. Cheap CSS-only animation;
       the gradient sweeps across each bar on a 1.4s loop. */
    .skeleton {
      display: flex; flex-direction: column; gap: 10px;
      width: 100%; padding: 8px 4px;
    }
    .skel-bar {
      display: block; height: 14px;
      border-radius: 7px;
      background: linear-gradient(
        90deg,
        var(--snm-skeleton-from, rgba(26, 58, 92, 0.06)) 0%,
        var(--snm-skeleton-mid,  rgba(26, 58, 92, 0.12)) 50%,
        var(--snm-skeleton-from, rgba(26, 58, 92, 0.06)) 100%
      );
      background-size: 200% 100%;
      animation: kpi-shimmer 1.4s ease-in-out infinite;
    }
    .skel-bar.w-40 { width: 40%; }
    .skel-bar.w-60 { width: 60%; }
    .skel-bar.w-75 { width: 75%; }
    .skel-bar.w-90 { width: 90%; }
    @keyframes kpi-shimmer {
      0%   { background-position: 100% 0; }
      100% { background-position: -100% 0; }
    }

    /* Refresh pulse — sits over the existing chart on re-runs so the
       user knows the data is being fetched without blanking the
       card. Two-second slow blue glow loop. */
    .refresh-pulse {
      position: absolute; top: 0; left: 0; right: 0;
      height: 3px;
      background: linear-gradient(
        90deg,
        transparent 0%,
        var(--snm-accent, #4a90e2) 50%,
        transparent 100%
      );
      background-size: 200% 100%;
      animation: kpi-refresh-pulse 1.4s linear infinite;
      pointer-events: none;
      z-index: 3;
    }
    @keyframes kpi-refresh-pulse {
      0%   { background-position: 100% 0; }
      100% { background-position: -100% 0; }
    }
    .error {
      display: flex; flex-direction: column; align-items: center; gap: 8px;
      color: var(--snm-text-muted); padding: 12px; text-align: center; font-size: 0.85rem;
      mat-icon { color: var(--snm-error, #e53935); }
    }
  `],
})
export class KpiCardComponent implements OnInit {
  private readonly kpis = inject(KpiService);
  private readonly destroyRef = inject(DestroyRef);

  readonly item = input.required<DashboardItem>();
  readonly editable = input(false);
  /** Show inline resize arrows in the card head. Independent from
   * ``editable`` (which gates the full options menu) — the unified
   * dashboard page wants resize without the rest of the edit chrome. */
  readonly showResize = input(false);
  /** Period filter applied to ``/kpis/{id}/run``. Null = all-time. The
   * card auto-reloads whenever the value changes. */
  readonly period = input<TimePeriodSelection | null>(null);

  readonly resize = output<CardSize>();
  readonly remove = output<void>();

  readonly sizes = CARD_SIZES;
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly result = signal<ExecutionResult | null>(null);

  /** Phase J.2 — short labels for each per-card filter, shown as
   * chips under the card title so the viewer knows the data is sliced.
   * Format: ``<column> <op> <value>`` (e.g. ``region = North``). */
  readonly filterChips = computed<string[]>(() => {
    const filters = this.item().extra_filters ?? [];
    return filters.map(f => {
      const op = f.op;
      if (op === 'is_null') return `${f.column} is null`;
      if (op === 'is_not_null') return `${f.column} not null`;
      if (op === 'in' || op === 'not_in') {
        const list = Array.isArray(f.value) ? f.value.join(', ') : String(f.value ?? '');
        return `${f.column} ${op === 'in' ? 'in' : 'not in'} (${list})`;
      }
      if (op === 'between' && Array.isArray(f.value) && f.value.length === 2) {
        return `${f.column} between ${f.value[0]}–${f.value[1]}`;
      }
      return `${f.column} ${op} ${f.value}`;
    });
  });

  readonly effectiveChartConfig = computed(() => {
    // Priority order:
    //   1. The saved chart_config on the KPI definition — the author's
    //      explicit choice. Includes type + per-chart config (axis /
    //      value mapping) + style (theme / animations).
    //   2. The executor's auto-suggestion — only when (1) is missing
    //      (legacy KPIs that pre-date the saved config).
    // Always coercing to (1) used to silently rewrite the chart type
    // every time a card was rendered, breaking author intent.
    //
    // Phase J.2 — per-card axis-label overrides (set by AI Polish)
    // merge into the chart_config's ``config`` block. A non-null
    // override replaces the KPI-level value; null/undefined falls
    // back to whatever the KPI authored (which itself may be empty).
    const it = this.item();
    const saved = it.kpi_chart_config;
    const baseType = saved?.type ?? this.result()?.suggestion?.type;
    if (!baseType) return null;
    const baseConfig = saved?.config ?? this.result()?.suggestion?.config ?? {};
    const merged = { ...baseConfig };
    if (it.x_label != null) merged['x_label'] = it.x_label;
    if (it.y_label != null) merged['y_label'] = it.y_label;
    return { type: baseType, config: merged, style: saved?.style ?? {} };
  });

  constructor() {
    // Reload whenever the period input changes — but only after first init,
    // ngOnInit handles the initial load. The ``hasInited`` guard avoids a
    // double-fire on mount (effect runs once at creation time).
    let hasInited = false;
    effect(() => {
      // Touch ``period`` so the effect re-runs when it changes.
      this.period();
      // Touch the per-card filter signature so AI Polish edits flow
      // straight through into a re-run without the host having to
      // poke the card. JSON.stringify gives us a cheap deep-equality
      // signature — extra_filters is short (<= 3 items by design).
      JSON.stringify(this.item().extra_filters ?? []);
      if (hasInited) {
        this.reload();
      } else {
        hasInited = true;
      }
    });
  }

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    if (!this.item().kpi_is_active) return;
    this.loading.set(true);
    this.error.set(null);
    const sel = this.period();
    this.kpis.run(this.item().kpi_id, {
      period: sel?.period ?? null,
      start_date: sel?.start_date ?? null,
      end_date: sel?.end_date ?? null,
      // Phase J.2 — per-card filters merge with the KPI's saved spec
      // at execute time (only honored on builder-mode KPIs; raw-SQL
      // KPIs ignore them — backend decides).
      extra_filters: this.item().extra_filters ?? [],
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: r => {
          this.loading.set(false);
          this.result.set(r);
        },
        error: err => {
          this.loading.set(false);
          this.error.set(err?.error?.detail?.message ?? err?.error?.detail ?? 'Failed to run KPI');
        },
      });
  }

  sizeLabel(s: CardSize): string {
    return CARD_SIZE_LABELS[s];
  }

  /** Step the card's size_class one notch in either direction. Emits
   * the new size — host (e.g. dashboard page) decides whether to
   * persist it. */
  stepSize(direction: -1 | 1): void {
    const current = CARD_SIZES.indexOf(this.item().size_class);
    const next = current + direction;
    if (next < 0 || next >= CARD_SIZES.length) return;
    this.resize.emit(CARD_SIZES[next]);
  }

  canShrink(): boolean {
    return CARD_SIZES.indexOf(this.item().size_class) > 0;
  }

  canGrow(): boolean {
    return CARD_SIZES.indexOf(this.item().size_class) < CARD_SIZES.length - 1;
  }
}
