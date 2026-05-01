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
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { KpiService } from '../../services/kpi.service';
import { KpiSummary } from '../../models/schema.types';

@Component({
  selector: 'app-add-kpi-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    MatButtonModule, MatDialogModule, MatFormFieldModule, MatInputModule,
    MatIconModule, MatChipsModule, MatProgressSpinnerModule,
  ],
  template: `
    <h2 mat-dialog-title>Add KPI to dashboard</h2>
    <mat-dialog-content>
      <mat-form-field appearance="outline" class="full">
        <mat-label>Search KPIs</mat-label>
        <input matInput type="search"
               [ngModel]="search()" (ngModelChange)="search.set($event)"
               cdkFocusInitial>
        <mat-icon matSuffix>search</mat-icon>
      </mat-form-field>

      <div class="loading" *ngIf="loading()">
        <mat-spinner diameter="28"></mat-spinner>
      </div>

      <ul class="kpi-list" *ngIf="!loading()">
        <li *ngFor="let k of filtered()" (click)="pick(k)" class="kpi-row">
          <div>
            <strong>{{ k.name }}</strong>
            <p class="desc">{{ k.description || 'No description.' }}</p>
          </div>
          <mat-chip class="chip" disabled>{{ k.chart_type }}</mat-chip>
        </li>
        <li *ngIf="!filtered().length" class="empty">No KPIs match.</li>
      </ul>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button [mat-dialog-close]="null">Cancel</button>
    </mat-dialog-actions>
  `,
  styles: [`
    .full { width: 100%; }
    .loading { display: flex; justify-content: center; padding: 16px; }
    .kpi-list { list-style: none; margin: 0; padding: 0; max-height: 320px; overflow-y: auto; }
    .kpi-row {
      display: flex; justify-content: space-between; align-items: center; gap: 8px;
      padding: 10px 12px; border-radius: 6px; cursor: pointer;
      border: 1px solid transparent;
    }
    .kpi-row:hover {
      background: var(--snm-bg-panel, #f5f5f5);
      border-color: var(--snm-accent, #4a90e2);
    }
    .desc { margin: 2px 0 0; font-size: 0.8rem; color: var(--snm-text-muted); }
    .chip { font-size: 0.65rem; }
    .empty { color: var(--snm-text-muted); padding: 16px; text-align: center; font-style: italic; }
  `],
})
export class AddKpiDialogComponent implements OnInit {
  private readonly kpis = inject(KpiService);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(false);
  readonly all = signal<KpiSummary[]>([]);
  readonly search = signal('');

  readonly filtered = computed(() => {
    const q = this.search().trim().toLowerCase();
    if (!q) return this.all();
    return this.all().filter(k =>
      k.name.toLowerCase().includes(q)
      || (k.description ?? '').toLowerCase().includes(q),
    );
  });

  constructor(private readonly ref: MatDialogRef<AddKpiDialogComponent>) {}

  ngOnInit(): void {
    this.loading.set(true);
    this.kpis.list()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: r => { this.all.set(r.items); this.loading.set(false); },
        error: () => { this.loading.set(false); this.all.set([]); },
      });
  }

  pick(k: KpiSummary): void {
    this.ref.close(k);
  }
}
