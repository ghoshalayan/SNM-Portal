import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';

@Component({
  selector: 'app-item-name-dialog',
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
  ],
  template: `
    <h2 mat-dialog-title>{{ isEdit ? 'Edit' : 'Add' }} Item Name</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="dialog-form">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Item Grade</mat-label>
          <mat-select formControlName="itemGradeId" panelClass="searchable-panel">
            <div class="select-search" (click)="$event.stopPropagation()">
              <mat-icon class="search-ico">search</mat-icon>
              <input placeholder="Search grades..."
                [value]="gradeSearch"
                (input)="gradeSearch = $any($event.target).value; filterGrades()"
                (keydown)="$event.stopPropagation()">
            </div>
            @for (g of displayedGrades; track g.itemGradeId) {
              <mat-option [value]="g.itemGradeId">{{ g.itemGradeName }}</mat-option>
            }
          </mat-select>
          <mat-error *ngIf="form.get('itemGradeId')?.hasError('required')">Required</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Item Name</mat-label>
          <input matInput formControlName="itemName" placeholder="Enter item name" />
          <mat-error *ngIf="form.get('itemName')?.hasError('required')">Required</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Item Dia</mat-label>
          <input matInput formControlName="itemDia" placeholder="Enter dia" />
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Item Length</mat-label>
          <input matInput formControlName="itemLength" placeholder="Enter length" />
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>ERP Item Code</mat-label>
          <input matInput formControlName="erpItemCode" placeholder="Enter ERP item code" />
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>ERP Name</mat-label>
          <input matInput formControlName="erpName" placeholder="Enter ERP name" />
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
  styles: [`.dialog-form { display: flex; flex-direction: column; gap: 12px; min-width: 440px; padding-top: 8px; } .full-width { width: 100%; }`],
})
export class ItemNameDialogComponent implements OnInit {
  form!: FormGroup;
  isEdit = false;
  saving = false;
  grades: any[] = [];
  displayedGrades: any[] = [];
  gradeSearch = '';

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private notify: NotificationService,
    private dialogRef: MatDialogRef<ItemNameDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
  ) {}

  ngOnInit() {
    this.isEdit = !!this.data;
    this.form = this.fb.group({
      itemGradeId: [this.data?.itemGradeId || '', Validators.required],
      itemName: [this.data?.itemName || '', Validators.required],
      itemDia: [this.data?.itemDia || ''],
      itemLength: [this.data?.itemLength || ''],
      erpItemCode: [this.data?.erpItemCode || ''],
      erpName: [this.data?.erpName || ''],
    });
    this.api.get('/masters/item-grades').subscribe({
      next: (res: any) => {
        this.grades = res || [];
        this.displayedGrades = [...this.grades];
      },
      error: () => this.notify.error('Failed to load item grades'),
    });
  }

  filterGrades(): void {
    const term = this.gradeSearch.toLowerCase();
    this.displayedGrades = term
      ? this.grades.filter(g => g.itemGradeName.toLowerCase().includes(term))
      : [...this.grades];
  }

  save() {
    if (this.form.invalid) return;
    this.saving = true;
    const payload = this.form.value;
    const call = this.isEdit
      ? this.api.put(`/masters/item-names/${this.data.itemId}`, payload)
      : this.api.post('/masters/item-names', payload);
    call.subscribe({
      next: () => {
        this.notify.success(`Item name ${this.isEdit ? 'updated' : 'created'} successfully`);
        this.dialogRef.close(true);
      },
      error: () => { this.notify.error('Save failed'); this.saving = false; },
    });
  }
}
