import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { MatIconModule } from '@angular/material/icon';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';

@Component({
  selector: 'app-raw-material-cost-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatSelectModule,
    MatIconModule,
    MatDatepickerModule,
    MatCheckboxModule,
  ],
  template: `
    <h2 mat-dialog-title>{{ isEdit ? 'Edit' : 'Add' }} Raw Material Cost</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="dialog-form">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Dia</mat-label>
          <mat-select formControlName="dia" panelClass="searchable-panel">
            <div class="select-search" (click)="$event.stopPropagation()">
              <mat-icon class="search-ico">search</mat-icon>
              <input placeholder="Search dia..."
                [value]="diaSearch"
                (input)="diaSearch = $any($event.target).value; filterDias()"
                (keydown)="$event.stopPropagation()">
            </div>
            @for (d of displayedDias; track d.diaid) {
              <mat-option [value]="d.diadescription">{{ d.diadescription }}</mat-option>
            }
          </mat-select>
          <mat-error *ngIf="form.get('dia')?.hasError('required')">Required</mat-error>
        </mat-form-field>

        <!-- Base Price Checkbox -->
        <div class="base-price-row">
          <mat-checkbox formControlName="isBasePrice" color="primary"
            (change)="onBasePriceToggle()">
            <strong>Base Price</strong>
          </mat-checkbox>
          <span class="base-hint" *ngIf="form.get('isBasePrice')?.value">
            This dia's cost will be the reference for all other dias
          </span>
        </div>

        <!-- Base Price row: just enter TP Cost directly -->
        <mat-form-field appearance="outline" class="full-width" *ngIf="form.get('isBasePrice')?.value">
          <mat-label>TP Cost (Base Price)</mat-label>
          <input matInput type="number" formControlName="tpcost" />
          <mat-error *ngIf="form.get('tpcost')?.hasError('required')">Required</mat-error>
        </mat-form-field>

        <!-- Non-base row: show inherited base + difference + computed final -->
        <ng-container *ngIf="!form.get('isBasePrice')?.value">
          <div class="derived-cost-section">
            <mat-form-field appearance="outline" class="cost-field">
              <mat-label>Base TP Cost</mat-label>
              <input matInput type="number" [value]="baseTpCost" readonly class="readonly-field" />
              <mat-hint *ngIf="baseDia">From {{ baseDia }} (base dia)</mat-hint>
              <mat-hint *ngIf="!baseDia" class="warn-hint">No base price set</mat-hint>
            </mat-form-field>

            <span class="operator">+</span>

            <mat-form-field appearance="outline" class="cost-field">
              <mat-label>Difference</mat-label>
              <input matInput type="number" formControlName="diffFromBase"
                (ngModelChange)="computeFinalCost()" />
            </mat-form-field>

            <span class="operator">=</span>

            <mat-form-field appearance="outline" class="cost-field">
              <mat-label>Final TP Cost</mat-label>
              <input matInput type="number" formControlName="tpcost" readonly class="readonly-field final-cost" />
            </mat-form-field>
          </div>
        </ng-container>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Effected From</mat-label>
          <input matInput [matDatepicker]="picker" formControlName="effectedFrom"
            [min]="minDate" />
          <mat-datepicker-toggle matIconSuffix [for]="picker"></mat-datepicker-toggle>
          <mat-datepicker #picker></mat-datepicker>
          <mat-hint>Back-dates are not allowed</mat-hint>
          <mat-error *ngIf="form.get('effectedFrom')?.hasError('required')">Required</mat-error>
        </mat-form-field>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-raised-button color="primary" (click)="save()" [disabled]="form.invalid || saving">
        {{ saving ? 'Saving...' : 'Save' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .dialog-form { display: flex; flex-direction: column; gap: 12px; min-width: 400px; padding-top: 8px; }
    .full-width { width: 100%; }
    .base-price-row {
      display: flex; align-items: center; gap: 12px; margin: 4px 0;
    }
    .base-hint { font-size: 12px; color: #1565c0; }
    .derived-cost-section {
      display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
      margin-bottom: 12px;
    }
    .cost-field { flex: 1; min-width: 120px; }
    .operator { font-size: 20px; font-weight: 700; color: #888; padding-top: 8px; }
    .final-cost { font-weight: 700; color: #1565c0 !important; }
    .warn-hint { color: #e65100 !important; }
  `],
})
export class RawMaterialCostDialogComponent implements OnInit {
  form!: FormGroup;
  isEdit = false;
  saving = false;
  dias: any[] = [];
  displayedDias: any[] = [];
  diaSearch = '';
  baseTpCost: number = 0;
  baseDia: string = '';
  minDate = new Date();  // Lock back-dates

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private notify: NotificationService,
    private dialogRef: MatDialogRef<RawMaterialCostDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
  ) {}

  ngOnInit() {
    this.isEdit = !!this.data;
    const isBase = this.data?.isBasePrice ?? false;
    this.form = this.fb.group({
      dia: [this.data?.dia || '', Validators.required],
      tpcost: [this.data?.tpcost ?? null, Validators.required],
      effectedFrom: [this.data?.effectedFrom ? new Date(this.data.effectedFrom) : null, Validators.required],
      isBasePrice: [isBase],
      diffFromBase: [this.data?.diffFromBase ?? 0],
    });

    // Load dias
    this.api.get('/masters/dia-masters').subscribe({
      next: (res: any) => {
        this.dias = res || [];
        this.displayedDias = [...this.dias];
      },
      error: () => this.notify.error('Failed to load dia list'),
    });

    // Load base price
    this.loadBasePrice();
  }

  loadBasePrice(): void {
    this.api.get<any>('/masters/raw-material-costs/base-price').subscribe({
      next: (bp) => {
        if (bp) {
          this.baseTpCost = bp.tpcost;
          this.baseDia = bp.dia;
          // If editing a non-base row and tpcost is set but diffFromBase isn't, compute it
          if (this.isEdit && !this.form.get('isBasePrice')?.value && this.data?.diffFromBase == null) {
            const currentCost = this.data?.tpcost || 0;
            this.form.get('diffFromBase')?.setValue(currentCost - this.baseTpCost);
          }
        }
      },
    });
  }

  onBasePriceToggle(): void {
    if (this.form.get('isBasePrice')?.value) {
      // Switching to base: clear difference, user enters tpcost directly
      this.form.get('diffFromBase')?.setValue(null);
      this.form.get('tpcost')?.enable();
    } else {
      // Switching to derived: compute from base + difference
      this.computeFinalCost();
    }
  }

  computeFinalCost(): void {
    const diff = Number(this.form.get('diffFromBase')?.value) || 0;
    const final = this.baseTpCost + diff;
    this.form.get('tpcost')?.setValue(Math.round(final * 100) / 100);
  }

  filterDias(): void {
    const term = this.diaSearch.toLowerCase();
    this.displayedDias = term
      ? this.dias.filter((d: any) => d.diadescription.toLowerCase().includes(term))
      : [...this.dias];
  }

  save() {
    if (this.form.invalid) return;
    this.saving = true;
    const payload = { ...this.form.value };
    if (payload.effectedFrom instanceof Date) {
      // Use local date (not UTC) to avoid timezone shift (IST → UTC loses 1 day)
      const d = payload.effectedFrom;
      payload.effectedFrom = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    }
    // For base row, clear diffFromBase
    if (payload.isBasePrice) {
      payload.diffFromBase = null;
    }
    const call = this.isEdit
      ? this.api.put(`/masters/raw-material-costs/${this.data.rawMaterialCostId}`, payload)
      : this.api.post('/masters/raw-material-costs', payload);
    call.subscribe({
      next: () => {
        this.notify.success(`Raw material cost ${this.isEdit ? 'updated' : 'created'} successfully`);
        this.dialogRef.close(true);
      },
      error: () => { this.notify.error('Save failed'); this.saving = false; },
    });
  }
}
