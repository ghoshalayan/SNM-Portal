import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ServerSearchSelectComponent } from '../server-search-select/server-search-select.component';

export interface HandoverDialogData {
  /** Entity type: 'enquiry' or 'quotation' */
  entityType: 'enquiry' | 'quotation';
  /** Primary key of the entity */
  entityId: number;
  /** Display identifier (e.g. ENQ/QUOT number) shown in dialog header */
  entityNo?: string;
  /** Current owner userId (to exclude from picker) */
  currentOwnerUserId?: number;
}

@Component({
  selector: 'app-handover-dialog',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatDialogModule, MatFormFieldModule,
    MatInputModule, MatSelectModule, MatButtonModule, MatIconModule,
    MatProgressSpinnerModule, ServerSearchSelectComponent,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon>swap_horiz</mat-icon>
      Transfer Ownership — {{ data.entityNo || ('#' + data.entityId) }}
    </h2>
    <mat-dialog-content>
      <p class="info">
        Transfer this {{ data.entityType }} to another user. The new owner will
        have full access to the record.
        @if (data.entityType === 'quotation') {
          <br><strong>Note:</strong> Approved quotations will revert to Draft on transfer.
        }
      </p>

      <app-server-search-select
        endpoint="/users/search"
        label="Target User"
        placeholder="Search user by name or code..."
        [(ngModel)]="targetUserId">
      </app-server-search-select>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Remarks (optional)</mat-label>
        <textarea matInput [(ngModel)]="remarks" rows="2"
          placeholder="Reason for transfer..."></textarea>
      </mat-form-field>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-stroked-button (click)="close()">Cancel</button>
      <button mat-raised-button color="primary"
        (click)="confirm()"
        [disabled]="!targetUserId || saving">
        <mat-spinner *ngIf="saving" diameter="16" class="inline-spinner"></mat-spinner>
        {{ saving ? 'Transferring...' : 'Confirm Transfer' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host mat-dialog-content { min-width: 480px; }
    .info { color: rgba(0,0,0,.7); font-size: 13px; margin: 0 0 16px; }
    .full-width { width: 100%; margin-bottom: 8px; }
    .loading { display: flex; justify-content: center; padding: 24px; }
    .code { color: #1976d2; font-weight: 500; }
    .select-search {
      position: sticky; top: 0; background: #fff; z-index: 1;
      padding: 6px 10px; display: flex; align-items: center; gap: 6px;
      border-bottom: 1px solid #eee;
    }
    .select-search input {
      border: 1px solid #ccc; border-radius: 4px; padding: 4px 8px;
      flex: 1; outline: none; font-size: 13px;
    }
    .search-ico { color: #888; font-size: 18px; }
    h2[mat-dialog-title] { display: flex; align-items: center; gap: 8px; }
    .inline-spinner { display: inline-block; margin-right: 6px; }
  `],
})
export class HandoverDialogComponent {
  targetUserId: number | null = null;
  remarks = '';
  saving = false;

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    private dialogRef: MatDialogRef<HandoverDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: HandoverDialogData,
  ) {}

  confirm(): void {
    if (!this.targetUserId) return;
    this.saving = true;
    const path = this.data.entityType === 'enquiry'
      ? `/enquiries/${this.data.entityId}/handover`
      : `/quotations/${this.data.entityId}/handover`;
    this.api.post(path, {
      targetUserId: this.targetUserId,
      remarks: this.remarks || null,
    }).subscribe({
      next: () => {
        this.notify.success('Ownership transferred');
        this.dialogRef.close(true);
      },
      error: (err) => {
        const msg = err?.error?.detail || 'Transfer failed';
        this.notify.error(msg);
        this.saving = false;
      },
    });
  }

  close(): void {
    this.dialogRef.close(null);
  }
}
