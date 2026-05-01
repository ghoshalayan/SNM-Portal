import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';

@Component({
  selector: 'app-enq-status-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
  ],
  template: `
    <h2 mat-dialog-title>{{ isEdit ? 'Edit' : 'Add' }} Enquiry Status</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="dialog-form">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Enquiry Status</mat-label>
          <input matInput formControlName="enqStatus" placeholder="Enter enquiry status" />
          <mat-error *ngIf="form.get('enqStatus')?.hasError('required')">Required</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Step No</mat-label>
          <input matInput type="number" formControlName="stepno" placeholder="Enter step number" />
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
export class EnqStatusDialogComponent implements OnInit {
  form!: FormGroup;
  isEdit = false;
  saving = false;

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private notify: NotificationService,
    private dialogRef: MatDialogRef<EnqStatusDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
  ) {}

  ngOnInit() {
    this.isEdit = !!this.data;
    this.form = this.fb.group({
      enqStatus: [this.data?.enqStatus || '', Validators.required],
      stepno: [this.data?.stepno || null],
    });
  }

  save() {
    if (this.form.invalid) return;
    this.saving = true;
    const payload = this.form.value;
    const call = this.isEdit
      ? this.api.put(`/masters/enq-statuses/${this.data.enqstatid}`, payload)
      : this.api.post('/masters/enq-statuses', payload);
    call.subscribe({
      next: () => {
        this.notify.success(`Enquiry status ${this.isEdit ? 'updated' : 'created'} successfully`);
        this.dialogRef.close(true);
      },
      error: () => { this.notify.error('Save failed'); this.saving = false; },
    });
  }
}
