import { Component, Input, OnInit, OnChanges, SimpleChanges, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatDividerModule } from '@angular/material/divider';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';

export interface QuotFollowUp {
  quotfollowupid?: number;
  quotId?: number;
  followupdate: string | null;
  followupremarks: string;
  followupmode: string;
  nextfollowupdate: string | null;
  createdon?: string;
}

const FOLLOWUP_MODES = [
  { value: 'PHONE', label: 'Phone' },
  { value: 'EMAIL', label: 'Email' },
  { value: 'VISIT', label: 'Visit' },
  { value: 'WHATSAPP', label: 'WhatsApp' },
  { value: 'ONLINE', label: 'Online Meeting' },
  { value: 'OTHER', label: 'Other' },
];

// ===== Follow-Up Dialog =====
@Component({
  selector: 'app-quot-followup-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatDialogModule,
    MatDatepickerModule,
    MatNativeDateModule,
  ],
  template: `
    <h2 mat-dialog-title>{{ data.followup?.quotfollowupid ? 'Edit Follow-Up' : 'Add Follow-Up' }}</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="followup-form">
        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Follow-Up Date *</mat-label>
            <input matInput [matDatepicker]="fuDatePicker" formControlName="followupdate" />
            <mat-datepicker-toggle matIconSuffix [for]="fuDatePicker"></mat-datepicker-toggle>
            <mat-datepicker #fuDatePicker></mat-datepicker>
            <mat-error *ngIf="form.get('followupdate')?.hasError('required')">Required</mat-error>
          </mat-form-field>

          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Mode *</mat-label>
            <mat-select formControlName="followupmode">
              <mat-option *ngFor="let m of modes" [value]="m.value">{{ m.label }}</mat-option>
            </mat-select>
            <mat-error *ngIf="form.get('followupmode')?.hasError('required')">Required</mat-error>
          </mat-form-field>
        </div>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Remarks</mat-label>
          <textarea matInput formControlName="followupremarks" rows="3"
            placeholder="Enter follow-up notes..."></textarea>
        </mat-form-field>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Next Follow-Up Date</mat-label>
          <input matInput [matDatepicker]="nextPicker" formControlName="nextfollowupdate" />
          <mat-datepicker-toggle matIconSuffix [for]="nextPicker"></mat-datepicker-toggle>
          <mat-datepicker #nextPicker></mat-datepicker>
        </mat-form-field>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-stroked-button (click)="cancel()">Cancel</button>
      <button mat-raised-button color="primary" (click)="save()" [disabled]="form.invalid">
        {{ data.followup?.quotfollowupid ? 'Update' : 'Add' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .followup-form { min-width: 460px; padding: 8px 0; }
    .form-row { display: flex; gap: 16px; }
    .half-width { flex: 1; }
    .full-width { width: 100%; }
  `],
})
export class QuotFollowUpDialogComponent {
  form: FormGroup;
  modes = FOLLOWUP_MODES;

  constructor(
    private fb: FormBuilder,
    private dialogRef: MatDialogRef<QuotFollowUpDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { followup: QuotFollowUp | null }
  ) {
    const f = data.followup;
    this.form = this.fb.group({
      followupdate: [f?.followupdate ? new Date(f.followupdate) : new Date(), Validators.required],
      followupmode: [f?.followupmode ?? '', Validators.required],
      followupremarks: [f?.followupremarks ?? ''],
      nextfollowupdate: [f?.nextfollowupdate ? new Date(f.nextfollowupdate) : null],
    });
  }

  save(): void {
    if (this.form.valid) {
      const val = { ...this.form.value };
      if (val.followupdate instanceof Date) {
        val.followupdate = `${val.followupdate.getFullYear()}-${String(val.followupdate.getMonth()+1).padStart(2,'0')}-${String(val.followupdate.getDate()).padStart(2,'0')}`;
      }
      if (val.nextfollowupdate instanceof Date) {
        val.nextfollowupdate = `${val.nextfollowupdate.getFullYear()}-${String(val.nextfollowupdate.getMonth()+1).padStart(2,'0')}-${String(val.nextfollowupdate.getDate()).padStart(2,'0')}`;
      }
      this.dialogRef.close(val);
    }
  }

  cancel(): void {
    this.dialogRef.close(null);
  }
}

// ===== Follow-Up List (Tab Content) =====
@Component({
  selector: 'app-quotation-followup',
  standalone: true,
  imports: [
    CommonModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
    MatProgressSpinnerModule,
    MatDialogModule,
    MatDividerModule,
  ],
  template: `
    <div class="followup-container">
      <div class="followup-toolbar">
        <span class="followup-title">Follow-Ups</span>
        <button mat-raised-button color="primary" (click)="openDialog(null)" [disabled]="!quotId">
          <mat-icon>add</mat-icon> Add Follow-Up
        </button>
      </div>

      <div class="loading-wrap" *ngIf="isLoading">
        <mat-spinner diameter="40"></mat-spinner>
      </div>

      <div class="table-wrapper" *ngIf="!isLoading">
        <table mat-table [dataSource]="dataSource" class="followup-table">

          <ng-container matColumnDef="followupdate">
            <th mat-header-cell *matHeaderCellDef>Date</th>
            <td mat-cell *matCellDef="let row">{{ row.followupdate | date:'dd-MM-yyyy' }}</td>
          </ng-container>

          <ng-container matColumnDef="followupmode">
            <th mat-header-cell *matHeaderCellDef>Mode</th>
            <td mat-cell *matCellDef="let row">
              <span class="mode-chip" [ngClass]="'mode-' + (row.followupmode || '').toLowerCase()">
                {{ getModeLabel(row.followupmode) }}
              </span>
            </td>
          </ng-container>

          <ng-container matColumnDef="followupremarks">
            <th mat-header-cell *matHeaderCellDef>Remarks</th>
            <td mat-cell *matCellDef="let row" class="remarks-cell">{{ row.followupremarks }}</td>
          </ng-container>

          <ng-container matColumnDef="nextfollowupdate">
            <th mat-header-cell *matHeaderCellDef>Next Follow-Up</th>
            <td mat-cell *matCellDef="let row">{{ row.nextfollowupdate ? (row.nextfollowupdate | date:'dd-MM-yyyy') : '—' }}</td>
          </ng-container>

          <ng-container matColumnDef="createdon">
            <th mat-header-cell *matHeaderCellDef>Created On</th>
            <td mat-cell *matCellDef="let row">{{ row.createdon | date:'dd-MM-yyyy HH:mm' }}</td>
          </ng-container>

          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef>Actions</th>
            <td mat-cell *matCellDef="let row">
              <button mat-icon-button color="primary" matTooltip="Edit" (click)="openDialog(row)">
                <mat-icon>edit</mat-icon>
              </button>
              <button mat-icon-button color="warn" matTooltip="Delete" (click)="deleteFollowUp(row)">
                <mat-icon>delete</mat-icon>
              </button>
            </td>
          </ng-container>

          <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
          <tr mat-row *matRowDef="let row; columns: displayedColumns"></tr>

          <tr class="mat-row" *matNoDataRow>
            <td class="mat-cell no-data-cell" [attr.colspan]="displayedColumns.length">
              No follow-ups recorded. Click "Add Follow-Up" to add one.
            </td>
          </tr>
        </table>
      </div>
    </div>
  `,
  styles: [`
    .followup-container { padding: 16px 0; }

    .followup-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
    }

    .followup-title {
      font-size: 16px;
      font-weight: 500;
      color: rgba(0, 0, 0, 0.87);
    }

    .loading-wrap {
      display: flex;
      justify-content: center;
      padding: 32px 0;
    }

    .table-wrapper { overflow-x: auto; }
    .followup-table { width: 100%; }

    .remarks-cell {
      max-width: 350px;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .no-data-cell {
      text-align: center;
      padding: 24px;
      color: rgba(0, 0, 0, 0.54);
    }

    .mode-chip {
      display: inline-block;
      padding: 2px 10px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 500;
      background: #e0e0e0;
      color: #333;
    }
    .mode-phone { background: #e8f5e9; color: #2e7d32; }
    .mode-email { background: #e3f2fd; color: #1565c0; }
    .mode-visit { background: #fff3e0; color: #e65100; }
    .mode-whatsapp { background: #e8f5e9; color: #1b5e20; }
    .mode-online { background: #f3e5f5; color: #7b1fa2; }
  `],
})
export class QuotationFollowUpComponent implements OnInit, OnChanges {
  @Input() quotId!: number | null;

  displayedColumns = ['followupdate', 'followupmode', 'followupremarks', 'nextfollowupdate', 'createdon', 'actions'];
  dataSource = new MatTableDataSource<QuotFollowUp>([]);
  isLoading = false;

  private modeMap = new Map(FOLLOWUP_MODES.map(m => [m.value, m.label]));

  constructor(
    private api: ApiService,
    private notification: NotificationService,
    private dialog: MatDialog,
  ) {}

  ngOnInit(): void {
    if (this.quotId) this.loadFollowUps();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['quotId'] && this.quotId) this.loadFollowUps();
  }

  getModeLabel(mode: string): string {
    return this.modeMap.get(mode) || mode || '—';
  }

  loadFollowUps(): void {
    if (!this.quotId) return;
    this.isLoading = true;
    this.api.get<QuotFollowUp[]>(`/quotations/${this.quotId}/followups`).subscribe({
      next: (data) => {
        this.dataSource.data = data;
        this.isLoading = false;
      },
      error: () => {
        this.notification.error('Failed to load follow-ups');
        this.isLoading = false;
      },
    });
  }

  openDialog(followup: QuotFollowUp | null): void {
    const dialogRef = this.dialog.open(QuotFollowUpDialogComponent, {
      data: { followup },
      width: '540px',
      disableClose: true,
    });

    dialogRef.afterClosed().subscribe((result: Partial<QuotFollowUp> | null) => {
      if (!result) return;

      if (followup?.quotfollowupid) {
        this.api
          .put(`/quotations/${this.quotId}/followups/${followup.quotfollowupid}`, result)
          .subscribe({
            next: () => {
              this.notification.success('Follow-up updated');
              this.loadFollowUps();
            },
            error: () => this.notification.error('Failed to update follow-up'),
          });
      } else {
        this.api
          .post(`/quotations/${this.quotId}/followups`, result)
          .subscribe({
            next: () => {
              this.notification.success('Follow-up added');
              this.loadFollowUps();
            },
            error: () => this.notification.error('Failed to add follow-up'),
          });
      }
    });
  }

  deleteFollowUp(followup: QuotFollowUp): void {
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Delete Follow-Up',
        message: 'Are you sure you want to delete this follow-up?',
        confirmText: 'Delete',
        cancelText: 'Cancel',
      },
    });

    dialogRef.afterClosed().subscribe((confirmed) => {
      if (confirmed) {
        this.api
          .delete(`/quotations/${this.quotId}/followups/${followup.quotfollowupid}`)
          .subscribe({
            next: () => {
              this.notification.success('Follow-up deleted');
              this.loadFollowUps();
            },
            error: () => this.notification.error('Failed to delete follow-up'),
          });
      }
    });
  }
}
