/**
 * Create-or-edit dialog for one KpiEvalCase.
 *
 * Single dialog handles both modes via `data.existing`:
 *  - null     → "New case", POST /eval/cases on save
 *  - present  → "Edit case", PUT /eval/cases/{id} on save
 *
 * Lists are entered as comma-separated values (tags, expected_tables,
 * expected_columns) — minimal UX for the SuperAdmin-only authoring
 * surface. Validation is server-side; the dialog just trims whitespace
 * and converts empty strings to nulls so the comparators skip them.
 */
import { CommonModule } from '@angular/common';
import { Component, Inject, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import {
  MAT_DIALOG_DATA, MatDialogModule, MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { NotificationService } from '../../../../core/services/notification.service';
import {
  EvalCase, EvalCaseCreate, EvalCaseUpdate,
} from '../../models/schema.types';
import { EvalService } from '../../services/eval.service';

export interface EvalCaseDialogData {
  existing: EvalCase | null;
}

@Component({
  selector: 'app-eval-case-dialog',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    MatButtonModule, MatCheckboxModule, MatDialogModule, MatFormFieldModule,
    MatIconModule, MatInputModule, MatProgressSpinnerModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="title-icon">science</mat-icon>
      {{ existing ? 'Edit case #' + existing.case_id : 'New eval case' }}
    </h2>
    <mat-dialog-content class="content">
      <mat-form-field appearance="outline" subscriptSizing="dynamic" class="full">
        <mat-label>Name</mat-label>
        <input matInput [(ngModel)]="form.name" required />
      </mat-form-field>

      <mat-form-field appearance="outline" subscriptSizing="dynamic" class="full">
        <mat-label>Prompt</mat-label>
        <textarea matInput rows="3" [(ngModel)]="form.prompt" required></textarea>
      </mat-form-field>

      <div class="row">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
          <mat-label>Tags (comma-separated)</mat-label>
          <input matInput [(ngModel)]="csv.tags"
                 placeholder="critical, regression, aggregation" />
        </mat-form-field>
      </div>

      <div class="row">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
          <mat-label>Expected tables (comma-separated)</mat-label>
          <input matInput [(ngModel)]="csv.expected_tables"
                 placeholder="CustomerMaster, QuotSummary" />
        </mat-form-field>
      </div>

      <div class="row">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
          <mat-label>Expected columns (qualified, comma-separated)</mat-label>
          <input matInput [(ngModel)]="csv.expected_columns"
                 placeholder="CustomerMaster.customerName, QuotSummary.totAmount" />
        </mat-form-field>
      </div>

      <div class="row">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="sm">
          <mat-label>Row count min</mat-label>
          <input matInput type="number" [(ngModel)]="form.expected_row_count_min" />
        </mat-form-field>
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="sm">
          <mat-label>Row count max</mat-label>
          <input matInput type="number" [(ngModel)]="form.expected_row_count_max" />
        </mat-form-field>
        <mat-checkbox [(ngModel)]="form.strict_tables">
          Strict tables (no extras allowed)
        </mat-checkbox>
      </div>

      <mat-form-field appearance="outline" subscriptSizing="dynamic" class="full">
        <mat-label>Golden SQL (optional — diff hint only, not compared verbatim)</mat-label>
        <textarea matInput rows="4" [(ngModel)]="form.golden_sql"
                  spellcheck="false" class="mono"></textarea>
      </mat-form-field>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button (click)="cancel()" [disabled]="saving">Cancel</button>
      <button mat-raised-button color="primary" (click)="save()"
              [disabled]="saving || !canSave">
        @if (saving) {
          <mat-spinner diameter="18" class="cta-spinner"></mat-spinner>
        }
        {{ existing ? 'Save' : 'Create' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .title-icon { vertical-align: middle; margin-right: 6px; color: var(--snm-accent); }
    .content {
      display: flex; flex-direction: column; gap: 10px;
      min-width: 520px; max-width: 92vw;
      padding-top: 6px;
    }
    .full { width: 100%; }
    .row {
      display: flex; gap: 10px; align-items: center;
      flex-wrap: wrap;
    }
    .grow { flex: 1 1 auto; min-width: 220px; }
    .sm { width: 140px; }
    textarea.mono {
      font-family: monospace; font-size: 12px; line-height: 1.4;
    }
    .cta-spinner { display: inline-block; vertical-align: middle; margin-right: 6px; }
  `],
})
export class EvalCaseDialogComponent {
  private readonly evalSvc = inject(EvalService);
  private readonly notify = inject(NotificationService);

  existing: EvalCase | null;
  saving = false;

  form: EvalCaseCreate & { is_active?: boolean } = {
    name: '',
    prompt: '',
    strict_tables: false,
    expected_row_count_min: null,
    expected_row_count_max: null,
    golden_sql: null,
  };
  csv = { tags: '', expected_tables: '', expected_columns: '' };

  constructor(
    public dialogRef: MatDialogRef<EvalCaseDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: EvalCaseDialogData,
  ) {
    this.existing = data.existing;
    if (this.existing) {
      this.form = {
        name: this.existing.name,
        prompt: this.existing.prompt,
        expected_row_count_min: this.existing.expected_row_count_min,
        expected_row_count_max: this.existing.expected_row_count_max,
        golden_sql: this.existing.golden_sql,
        strict_tables: this.existing.strict_tables,
      };
      this.csv.tags = (this.existing.tags || []).join(', ');
      this.csv.expected_tables = (this.existing.expected_tables || []).join(', ');
      this.csv.expected_columns = (this.existing.expected_columns || []).join(', ');
    }
  }

  get canSave(): boolean {
    return !!this.form.name.trim() && !!this.form.prompt.trim();
  }

  save(): void {
    if (!this.canSave) return;
    const payload: EvalCaseUpdate = {
      name: this.form.name.trim(),
      prompt: this.form.prompt.trim(),
      strict_tables: this.form.strict_tables,
      expected_tables: this.parseCsv(this.csv.expected_tables),
      expected_columns: this.parseCsv(this.csv.expected_columns),
      tags: this.parseCsv(this.csv.tags),
      expected_row_count_min: this.form.expected_row_count_min ?? null,
      expected_row_count_max: this.form.expected_row_count_max ?? null,
      golden_sql: (this.form.golden_sql || '').trim() || null,
    };

    this.saving = true;
    const obs$ = this.existing
      ? this.evalSvc.updateCase(this.existing.case_id, payload)
      : this.evalSvc.createCase(payload as EvalCaseCreate);

    obs$.subscribe({
      next: (saved) => {
        this.saving = false;
        this.notify.success(
          this.existing
            ? `Updated case #${this.existing.case_id}`
            : `Created case #${saved.case_id}`
        );
        this.dialogRef.close(saved);
      },
      error: (err) => {
        this.saving = false;
        this.notify.error(err?.error?.detail || 'Save failed');
      },
    });
  }

  cancel(): void {
    this.dialogRef.close(null);
  }

  private parseCsv(s: string): string[] | null {
    if (!s) return null;
    const parts = s.split(',').map(x => x.trim()).filter(Boolean);
    return parts.length ? parts : null;
  }
}
