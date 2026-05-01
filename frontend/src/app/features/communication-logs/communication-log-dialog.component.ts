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
import { ServerSearchSelectComponent } from '../../shared/components/server-search-select/server-search-select.component';

interface CommMode { commmodeId: number; commmode: string; }

@Component({
  selector: 'app-communication-log-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatDialogModule,
    MatFormFieldModule, MatInputModule, MatButtonModule, MatSelectModule,
    ServerSearchSelectComponent,
  ],
  template: `
    <h2 mat-dialog-title>{{ isEdit ? 'Edit' : 'Add' }} Communication Log</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="dialog-form">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Communication Mode</mat-label>
          <mat-select formControlName="commmode">
            @for (mode of commModes; track mode.commmodeId) {
              <mat-option [value]="mode.commmode">{{ mode.commmode }}</mat-option>
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

        <!-- Enquiry — searchable server-side dropdown showing enqNo
             instead of the raw enqid. Picking one resets the quotation
             field below and scopes the quotation dropdown to that
             enquiry's quotations only, so the user can never pair a
             quotation with the wrong enquiry. -->
        <app-server-search-select
          endpoint="/enquiries/search"
          label="Enquiry No"
          placeholder="Search enquiry by no..."
          formControlName="enqid"
          (selectionChange)="onEnquiryChange($event?.id || null)">
        </app-server-search-select>

        <!-- Quotation — same control, scoped to the selected enquiry
             via extraParams. When no enquiry is selected, the dropdown
             still works but lists all quotations the user can see. -->
        <app-server-search-select
          endpoint="/quotations/search"
          label="Quotation No"
          placeholder="Search quotation by no..."
          formControlName="quoteid"
          [extraParams]="quotationPickerParams">
        </app-server-search-select>

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
  /** Master rows: { commmodeId, commmode, ... }. We display & bind
   *  `.commmode` (the string label) — earlier code typed this as
   *  `string[]` which produced "[object Object]" in the dropdown. */
  commModes: CommMode[] = [];
  /** Extra query params for the quotation search-select. Updated when
   *  the user picks an enquiry so the quotation dropdown is scoped to
   *  that enquiry's quotations only — naturally enforces the rule that
   *  the picked quotation must belong to the picked enquiry. */
  quotationPickerParams: Record<string, string | number> = {};

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

    // If commModes weren't pre-loaded by the list, fetch them.
    if (this.commModes.length === 0) {
      this.api.get<CommMode[]>('/masters/communication-modes').subscribe({
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

    // If editing an existing row that already has an enquiry picked,
    // pre-scope the quotation dropdown so the resolved quoteid label
    // appears in context (and only sibling quotations show in the list).
    if (row?.enqid) {
      this.quotationPickerParams = { enqId: row.enqid };
    }
  }

  /** When the enquiry picker changes, reset the quotation field and
   *  re-scope the quotation dropdown to that enquiry. Choosing a
   *  quotation while the enquiry is null leaves the dropdown unscoped
   *  (lists all quotations the user can see). */
  onEnquiryChange(enqId: number | null): void {
    // Always clear quoteid — the previously selected quotation may not
    // belong to the newly chosen enquiry.
    this.form.get('quoteid')?.setValue(null);
    this.quotationPickerParams = enqId ? { enqId } : {};
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
