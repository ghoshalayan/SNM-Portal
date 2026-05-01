import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialog } from '@angular/material/dialog';
import { Subject, debounceTime } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { KpiService } from '../../services/kpi.service';
import { NlService } from '../../services/nl.service';
import { NotificationService } from '../../../../core/services/notification.service';
import { KpiSummary } from '../../models/schema.types';
import { ConfirmDialogComponent } from '../../../../shared/components/confirm-dialog/confirm-dialog.component';
import { FormattedError, formatHttpError } from '../../shared/error-format';
import { KpiErrorBannerComponent } from '../../shared/error-banner.component';
import { SuggestKpisDialogComponent } from '../../components/suggest-kpis-dialog/suggest-kpis-dialog.component';
import { MatTooltipModule } from '@angular/material/tooltip';

@Component({
  selector: 'app-kpi-list',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatButtonModule, MatIconModule, MatProgressBarModule,
    MatFormFieldModule, MatInputModule, MatSlideToggleModule, MatChipsModule,
    MatTooltipModule,
    KpiErrorBannerComponent,
  ],
  template: `
    <div class="kpi-list-page">
      <header class="page-header">
        <div>
          <h1>KPI Studio</h1>
          <p class="subtitle">{{ items().length }} of {{ total() }} KPIs.</p>
        </div>
        <div class="actions">
          <button mat-stroked-button color="primary"
                  *ngIf="aiEnabled()"
                  (click)="openSuggestDialog()"
                  matTooltip="Have the AI propose 5–8 ready-to-save KPIs for a table">
            <mat-icon>auto_awesome</mat-icon>
            AI Suggest
          </button>
          <button mat-flat-button color="primary"
                  routerLink="/kpi-studio/kpis/new">
            <mat-icon>add</mat-icon>
            New KPI
          </button>
        </div>
      </header>

      <div class="filters">
        <mat-form-field appearance="outline" class="search">
          <mat-label>Search</mat-label>
          <input matInput type="search"
                 [ngModel]="searchTerm()" (ngModelChange)="onSearch($event)">
          <mat-icon matSuffix>search</mat-icon>
        </mat-form-field>
        <mat-slide-toggle [checked]="includeInactive()"
                          (change)="toggleInactive($event.checked)">
          Show deleted
        </mat-slide-toggle>
      </div>

      <mat-progress-bar *ngIf="loading()" mode="indeterminate"></mat-progress-bar>

      <app-kpi-error-banner [error]="loadError()"
                             (retry)="load()"
                             (dismiss)="loadError.set(null)" />

      <div class="grid" *ngIf="!loading() || items().length">
        <button class="card"
                *ngFor="let k of items(); trackBy: trackKpi"
                (click)="open(k)">
          <div class="card-head">
            <span class="kpi-name">{{ k.name }}</span>
            <mat-chip class="chart-chip" disabled>{{ k.chart_type }}</mat-chip>
          </div>
          <p class="kpi-desc">{{ k.description || 'No description.' }}</p>
          <div class="card-foot">
            <span class="updated">Updated {{ k.updated_at | date:'short' }}</span>
            <span *ngIf="!k.is_active" class="deleted-pill">deleted</span>
            <span class="card-actions" (click)="$event.stopPropagation()">
              <button mat-icon-button matTooltip="Edit" (click)="open(k)">
                <mat-icon>edit</mat-icon>
              </button>
              <button mat-icon-button matTooltip="Delete" *ngIf="k.is_active"
                      (click)="confirmDelete(k)">
                <mat-icon>delete</mat-icon>
              </button>
            </span>
          </div>
        </button>
        <p *ngIf="!items().length && !loading()" class="empty">
          No KPIs yet. Click <strong>New KPI</strong> to create one.
        </p>
      </div>
    </div>
  `,
  styles: [`
    .kpi-list-page { padding: 24px; display: flex; flex-direction: column; gap: 16px; }
    .page-header { display: flex; justify-content: space-between; align-items: flex-start; }
    .page-header h1 { margin: 0; font-size: 1.5rem; color: var(--snm-text-primary); }
    .subtitle { margin: 4px 0 0; color: var(--snm-text-secondary); font-size: 0.85rem; }
    .filters { display: flex; gap: 16px; align-items: center; }
    .filters .search { flex: 1; max-width: 400px; }
    .grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 16px;
    }
    .card {
      background: var(--snm-bg-card, #fff);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 8px; padding: 16px; text-align: left; cursor: pointer;
      display: flex; flex-direction: column; gap: 8px;
      transition: border-color 120ms ease, transform 120ms ease;
    }
    .card:hover { border-color: var(--snm-accent, #4a90e2); transform: translateY(-1px); }
    .card-head {
      display: flex; justify-content: space-between; align-items: center; gap: 8px;
    }
    .kpi-name { font-weight: 600; color: var(--snm-text-primary); }
    .chart-chip { font-size: 0.7rem; }
    .kpi-desc {
      color: var(--snm-text-muted); font-size: 0.85rem; margin: 0;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .card-foot {
      display: flex; justify-content: space-between; align-items: center;
      font-size: 0.75rem; color: var(--snm-text-muted); margin-top: auto;
    }
    .deleted-pill {
      background: var(--snm-error, #e53935); color: white;
      padding: 2px 6px; border-radius: 3px; font-size: 0.65rem; text-transform: uppercase;
    }
    .empty { color: var(--snm-text-muted); padding: 32px; text-align: center;
             grid-column: 1 / -1; }
  `],
})
export class KpiListComponent implements OnInit {
  private readonly kpis = inject(KpiService);
  private readonly nl = inject(NlService);
  private readonly notify = inject(NotificationService);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(false);
  readonly items = signal<KpiSummary[]>([]);
  readonly total = signal(0);
  readonly searchTerm = signal('');
  readonly includeInactive = signal(false);
  readonly loadError = signal<FormattedError | null>(null);
  /** Phase J — AI suggest button is visible only when an LLM
   * provider is configured server-side (same gate as the editor's
   * "Generate from prompt"). */
  readonly aiEnabled = signal(false);

  private readonly searchSubject = new Subject<string>();

  ngOnInit(): void {
    this.searchSubject
      .pipe(debounceTime(350), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.load());
    this.load();
    this.nl.status()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: s => this.aiEnabled.set(s.enabled),
        error: () => this.aiEnabled.set(false),
      });
  }

  openSuggestDialog(): void {
    const ref = this.dialog.open(SuggestKpisDialogComponent, {
      width: '720px', maxWidth: '92vw',
      maxHeight: '92vh',
    });
    ref.afterClosed()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((createdIds: number[] | undefined) => {
        if (createdIds && createdIds.length) {
          this.notify.success(
            `${createdIds.length} KPI${createdIds.length === 1 ? '' : 's'} created.`,
          );
          this.load();
        }
      });
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.kpis.list({
      search: this.searchTerm() || undefined,
      includeInactive: this.includeInactive(),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: res => {
        this.items.set(res.items);
        this.total.set(res.total);
        this.loading.set(false);
      },
      error: err => {
        this.loading.set(false);
        this.loadError.set(formatHttpError(err, 'Failed to load KPIs'));
      },
    });
  }

  onSearch(v: string): void {
    this.searchTerm.set(v);
    this.searchSubject.next(v);
  }

  toggleInactive(checked: boolean): void {
    this.includeInactive.set(checked);
    this.load();
  }

  open(k: KpiSummary): void {
    this.router.navigate(['/kpi-studio/kpis', k.kpi_id]);
  }

  confirmDelete(k: KpiSummary): void {
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Delete KPI?',
        message: `"${k.name}" will be soft-deleted. Dashboards pinned to it will show a deleted placeholder.`,
        confirmText: 'Delete',
      },
    });
    ref.afterClosed().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(ok => {
      if (!ok) return;
      this.kpis.delete(k.kpi_id).subscribe({
        next: () => { this.notify.success('KPI deleted.'); this.load(); },
        error: err => this.notify.error(err?.error?.detail?.message ?? 'Delete failed'),
      });
    });
  }

  trackKpi = (_: number, k: KpiSummary) => k.kpi_id;
}
