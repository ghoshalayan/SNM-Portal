import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { ApiService } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';

@Component({
  selector: 'app-communication-log-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatDialogModule,
    MatFormFieldModule, MatInputModule, MatButtonModule, MatSelectModule,
  ],
  template: `
    <h2 mat-dialog-title>{{ isEdit ? 'Edit' : 'Add' }} Communication Log</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="dialog-form">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Communication Mode</mat-label>
          <mat-select formControlName="commmode">
            @for (mode of commModes; track mode) {
              <mat-option [value]="mode">{{ mode }}</mat-option>
            }
          </mat-select>
          <mat-error *ngIf="form.get('commmode')?.hasError('required')">Required</mat-error>
        </mat-form-field>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Contact To</mat-label>
          <input matInput formControlName="contactto" placeholder="Enter contact name" />
          <mat-error *ngIf="form.get('contactto')?.hasError('required')">Required</mat-error>
        </mat-form-field>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Contact Info</mat-label>
          <input matInput formControlName="contactinfo" placeholder="Enter contact info" />
          <mat-error *ngIf="form.get('contactinfo')?.hasError('required')">Required</mat-error>
        </mat-form-field>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Enquiry ID</mat-label>
          <input matInput type="number" formControlName="enqid" placeholder="Optional" />
        </mat-form-field>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Quotation ID</mat-label>
          <input matInput type="number" formControlName="quoteid" placeholder="Optional" />
        </mat-form-field>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Subject</mat-label>
          <input matInput formControlName="commsubject" placeholder="Enter subject" />
          <mat-error *ngIf="form.get('commsubject')?.hasError('required')">Required</mat-error>
        </mat-form-field>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Description</mat-label>
          <textarea matInput formControlName="commdescription" rows="4" placeholder="Enter description"></textarea>
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
export class CommunicationLogDialogComponent implements OnInit {
  form!: FormGroup;
  isEdit = false;
  saving = false;
  commModes: string[] = [];

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private notify: NotificationService,
    private dialogRef: MatDialogRef<CommunicationLogDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
  ) {}

  ngOnInit(): void {
    const row = this.data?.row;
    this.commModes = this.data?.commModes || [];
    this.isEdit = !!row;

    // If commModes were not passed, load them
    if (this.commModes.length === 0) {
      this.api.get<string[]>('/masters/communication-modes').subscribe({
        next: (data) => this.commModes = data || [],
      });
    }

    this.form = this.fb.group({
      commmode: [row?.commmode || '', Validators.required],
      contactto: [row?.contactto || '', Validators.required],
      contactinfo: [row?.contactinfo || '', Validators.required],
      enqid: [row?.enqid || null],
      quoteid: [row?.quoteid || null],
      commsubject: [row?.commsubject || '', Validators.required],
      commdescription: [row?.commdescription || ''],
    });
  }

  save(): void {
    if (this.form.invalid) return;
    this.saving = true;
    const payload = this.form.value;
    const call = this.isEdit
      ? this.api.put(`/communication-logs/${this.data.row.commlogID}`, payload)
      : this.api.post('/communication-logs', payload);
    call.subscribe({
      next: () => {
        this.notify.success(`Communication log ${this.isEdit ? 'updated' : 'created'} successfully`);
        this.dialogRef.close(true);
      },
      error: () => {
        this.notify.error('Save failed');
        this.saving = false;
      },
    });
  }
}
