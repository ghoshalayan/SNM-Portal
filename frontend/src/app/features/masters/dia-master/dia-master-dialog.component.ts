import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';

@Component({
  selector: 'app-dia-master-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatDialogModule,
    MatFormFieldModule, MatInputModule, MatButtonModule, MatSelectModule,
  ],
  template: `
    <h2 mat-dialog-title>{{ isEdit ? 'Edit' : 'Add' }} Dia</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="dialog-form">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Item Name</mat-label>
          <mat-select formControlName="itemid">
            <mat-option *ngFor="let item of itemNames" [value]="item.itemId">{{ item.itemName }}</mat-option>
          </mat-select>
          <mat-error *ngIf="form.get('itemid')?.hasError('required')">Required</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Dia Description</mat-label>
          <input matInput formControlName="diadescription" placeholder="Enter dia description" />
          <mat-error *ngIf="form.get('diadescription')?.hasError('required')">Required</mat-error>
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
  styles: [`.dialog-form { display: flex; flex-direction: column; gap: 12px; min-width: 360px; padding-top: 8px; } .full-width { width: 100%; }`],
})
export class DiaMasterDialogComponent implements OnInit {
  form!: FormGroup;
  isEdit = false;
  saving = false;
  itemNames: any[] = [];

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private notify: NotificationService,
    private dialogRef: MatDialogRef<DiaMasterDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
  ) {}

  ngOnInit() {
    const row = this.data?.row;
    this.itemNames = this.data?.itemNames || [];
    this.isEdit = !!row;
    this.form = this.fb.group({
      itemid: [row?.itemid || '', Validators.required],
      diadescription: [row?.diadescription || '', Validators.required],
    });
  }

  save() {
    if (this.form.invalid) return;
    this.saving = true;
    const payload = this.form.value;
    const call = this.isEdit
      ? this.api.put(`/masters/dia-masters/${this.data.row.diaid}`, payload)
      : this.api.post('/masters/dia-masters', payload);
    call.subscribe({
      next: () => {
        this.notify.success(`Dia ${this.isEdit ? 'updated' : 'created'} successfully`);
        this.dialogRef.close(true);
      },
      error: () => { this.notify.error('Save failed'); this.saving = false; },
    });
  }
}
