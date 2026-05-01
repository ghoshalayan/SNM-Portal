import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
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
import { MatSelectModule } from '@angular/material/select';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialog } from '@angular/material/dialog';
import { Subject, debounceTime } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { DashboardService } from '../../services/dashboard.service';
import { NotificationService } from '../../../../core/services/notification.service';
import { DashboardSummary } from '../../models/schema.types';
import { ConfirmDialogComponent } from '../../../../shared/components/confirm-dialog/confirm-dialog.component';
import { DashboardCreateDialogComponent } from './dashboard-create-dialog.component';
import { FormattedError, formatHttpError } from '../../shared/error-format';
import { KpiErrorBannerComponent } from '../../shared/error-banner.component';

@Component({
  selector: 'app-dashboards-list',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatButtonModule, MatIconModule, MatProgressBarModule,
    MatFormFieldModule, MatInputModule, MatSelectModule, MatChipsModule,
    KpiErrorBannerComponent,
  ],
  template: `
    <div class="page">
      <header class="page-header">
        <div>
          <h1>Dashboards</h1>
          <p class="subtitle">{{ items().length }} of {{ total() }}.</p>
        </div>
        <div class="actions">
          <a mat-stroked-button routerLink="/kpi-studio/kpis">
            <mat-icon>view_list</mat-icon>
            KPI library
          </a>
          <button mat-flat-button color="primary" (click)="openCreate()">
            <mat-icon>add</mat-icon>
            New dashboard
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
        <mat-form-field appearance="outline" class="scope-filter">
          <mat-label>Scope</mat-label>
          <mat-select [value]="scopeFilter()" (valueChange)="onScopeChange($event)">
            <mat-option [value]="">All</mat-option>
            <mat-option value="user">My private</mat-option>
            <mat-option value="company">Company shared</mat-option>
          </mat-select>
        </mat-form-field>
      </div>

      <mat-progress-bar *ngIf="loading()" mode="indeterminate"></mat-progress-bar>

      <app-kpi-error-banner [error]="loadError()"
                             (retry)="load()"
                             (dismiss)="loadError.set(null)" />

      <div class="grid" *ngIf="!loading() || items().length">
        <button class="card"
                *ngFor="let d of items(); trackBy: trackDash"
                (click)="open(d)">
          <div class="card-head">
            <span class="dash-name">{{ d.name }}</span>
            <mat-chip class="scope-chip" [class.shared]="d.scope === 'company'" disabled>
              {{ d.scope === 'company' ? 'shared' : 'private' }}
            </mat-chip>
          </div>
          <p class="dash-desc">{{ d.description || 'No description.' }}</p>
          <div class="card-foot">
            <span>{{ d.item_count }} card{{ d.item_count === 1 ? '' : 's' }}</span>
            <span>Updated {{ d.updated_at | date:'short' }}</span>
            <span class="card-actions" (click)="$event.stopPropagation()">
              <button mat-icon-button matTooltip="Edit"
                      (click)="openEdit(d)">
                <mat-icon>edit</mat-icon>
              </button>
              <button mat-icon-button matTooltip="Delete"
                      (click)="confirmDelete(d)">
                <mat-icon>delete</mat-icon>
              </button>
            </span>
          </div>
        </button>
        <p *ngIf="!items().length && !loading()" class="empty">
          No dashboards yet. Click <strong>New dashboard</strong> to create one.
        </p>
      </div>
    </div>
  `,
  styles: [`
    .page { padding: 24px; display: flex; flex-direction: column; gap: 16px; }
    .page-header { display: flex; justify-content: space-between; align-items: flex-start; }
    .page-header h1 { margin: 0; font-size: 1.5rem; color: var(--snm-text-primary); }
    .page-header .actions { display: flex; gap: 8px; }
    .subtitle { margin: 4px 0 0; color: var(--snm-text-secondary); font-size: 0.85rem; }
    .filters { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
    .filters .search { flex: 1; max-width: 400px; }
    .filters .scope-filter { width: 200px; }
    .grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px;
    }
    .card {
      background: var(--snm-bg-card, #fff);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 8px; padding: 16px; text-align: left; cursor: pointer;
      display: flex; flex-direction: column; gap: 8px;
      transition: border-color 120ms ease, transform 120ms ease;
    }
    .card:hover { border-color: var(--snm-accent, #4a90e2); transform: translateY(-1px); }
    .card-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
    .dash-name { font-weight: 600; color: var(--snm-text-primary); }
    .scope-chip { font-size: 0.7rem; }
    .scope-chip.shared {
      background: rgba(74, 144, 226, 0.12);
      color: var(--snm-accent);
    }
    .dash-desc {
      color: var(--snm-text-muted); font-size: 0.85rem; margin: 0;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .card-foot {
      display: flex; justify-content: space-between; align-items: center;
      font-size: 0.75rem; color: var(--snm-text-muted); margin-top: auto;
    }
    .empty { color: var(--snm-text-muted); padding: 32px; text-align: center;
             grid-column: 1 / -1; }
  `],
})
export class DashboardsListComponent implements OnInit {
  private readonly dashboards = inject(DashboardService);
  private readonly notify = inject(NotificationService);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(false);
  readonly items = signal<DashboardSummary[]>([]);
  readonly total = signal(0);
  readonly searchTerm = signal('');
  readonly scopeFilter = signal<'' | 'user' | 'company'>('');
  readonly loadError = signal<FormattedError | null>(null);

  private readonly searchSubject = new Subject<string>();

  ngOnInit(): void {
    this.searchSubject
      .pipe(debounceTime(350), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.load());
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.dashboards.list({
      search: this.searchTerm() || undefined,
      scope: this.scopeFilter() || undefined,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: res => {
        this.items.set(res.items);
        this.total.set(res.total);
        this.loading.set(false);
      },
      error: err => {
        this.loading.set(false);
        this.loadError.set(formatHttpError(err, 'Failed to load dashboards'));
      },
    });
  }

  onSearch(v: string): void {
    this.searchTerm.set(v);
    this.searchSubject.next(v);
  }

  onScopeChange(v: '' | 'user' | 'company'): void {
    this.scopeFilter.set(v);
    this.load();
  }

  open(d: DashboardSummary): void {
    this.router.navigate(['/kpi-studio/dashboards', d.dashboard_id]);
  }

  openEdit(d: DashboardSummary): void {
    this.router.navigate(['/kpi-studio/dashboards', d.dashboard_id, 'edit']);
  }

  openCreate(): void {
    const ref = this.dialog.open(DashboardCreateDialogComponent, { width: '460px' });
    ref.afterClosed().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(payload => {
      if (!payload) return;
      this.dashboards.create(payload).subscribe({
        next: d => {
          this.notify.success('Dashboard created.');
          this.router.navigate(['/kpi-studio/dashboards', d.dashboard_id, 'edit']);
        },
        error: err => this.notify.error(err?.error?.detail?.message ?? err?.error?.detail ?? 'Create failed'),
      });
    });
  }

  confirmDelete(d: DashboardSummary): void {
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Delete dashboard?',
        message: `"${d.name}" will be soft-deleted. KPIs are not affected.`,
        confirmText: 'Delete',
      },
    });
    ref.afterClosed().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(ok => {
      if (!ok) return;
      this.dashboards.delete(d.dashboard_id).subscribe({
        next: () => { this.notify.success('Dashboard deleted.'); this.load(); },
        error: err => this.notify.error(err?.error?.detail?.message ?? err?.error?.detail ?? 'Delete failed'),
      });
    });
  }

  trackDash = (_: number, d: DashboardSummary) => d.dashboard_id;
}
