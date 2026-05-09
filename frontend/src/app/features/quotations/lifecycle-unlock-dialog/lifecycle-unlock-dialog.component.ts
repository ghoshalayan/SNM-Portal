import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  MAT_DIALOG_DATA, MatDialogModule, MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';

export interface LifecycleUnlockDialogData {
  /** Quotation ID this stage hangs off. */
  quotationId: number;
  /** URL slug for the stage being unlocked. Accepted: 'quotation',
   *  'purchase-order', 'viability', 'annexure'. The dialog passes
   *  this through to the backend's generic unlock endpoint. */
  stage: 'quotation' | 'purchase-order' | 'viability' | 'annexure';
  /** Stage label shown in the dialog title. */
  stageLabel: string;
  /** Quotation no for context — surfaces in the audit trail. */
  quotNo?: string | null;
}

/**
 * Privileged escape valve. Posts to
 * ``POST /quotations/{id}/{stage}/unlock-edit`` with an optional
 * reason; the row is unchanged but a ``LifecycleUnlockAudit`` entry
 * is written. The frontend then unhides edit affordances on that
 * stage for the current session.
 *
 * Resolves with ``true`` on a successful unlock so the caller can
 * flip its local read-only flag; ``null`` on cancel/error.
 */
@Component({
  selector: 'app-lifecycle-unlock-dialog',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatDialogModule, MatFormFieldModule,
    MatInputModule, MatButtonModule, MatIconModule,
    MatProgressSpinnerModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon>lock_open</mat-icon>
      Unlock {{ data.stageLabel }} for editing
    </h2>
    <mat-dialog-content class="dialog-content">
      <p class="warn">
        <mat-icon class="warn-ico">warning_amber</mat-icon>
        This is a privileged action. The override is logged in the
        audit trail with your name, the time, and (if provided) the
        reason below — admins can review every unlock after the fact.
      </p>
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Reason (optional but recommended)</mat-label>
        <textarea matInput rows="3" maxlength="500" [(ngModel)]="reason"
          placeholder="e.g. Customer revised the PO terms; Commercial HOD asked for a typo fix"></textarea>
        <mat-hint>Up to 500 characters</mat-hint>
      </mat-form-field>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-stroked-button (click)="cancel()" [disabled]="saving">Cancel</button>
      <button mat-raised-button color="warn" (click)="confirm()" [disabled]="saving">
        <mat-spinner *ngIf="saving" diameter="16" class="inline-spinner"></mat-spinner>
        <mat-icon *ngIf="!saving">lock_open</mat-icon>
        Unlock {{ data.stageLabel }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host mat-dialog-content { min-width: 520px; }
    h2[mat-dialog-title] { display: flex; align-items: center; gap: 8px; }
    .warn {
      display: flex; align-items: flex-start; gap: 10px;
      padding: 12px 14px;
      background: rgba(245, 124, 0, 0.08);
      border-left: 3px solid #f57c00;
      border-radius: 4px;
      font-size: 13px;
      color: rgba(0,0,0,.78);
      margin: 0 0 16px;
    }
    .warn-ico { color: #f57c00; flex-shrink: 0; }
    .full-width { width: 100%; }
    .inline-spinner { display: inline-block; margin-right: 6px; }
  `],
})
export class LifecycleUnlockDialogComponent {
  reason = '';
  saving = false;

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    private dialogRef: MatDialogRef<LifecycleUnlockDialogComponent, boolean | null>,
    @Inject(MAT_DIALOG_DATA) public data: LifecycleUnlockDialogData,
  ) {}

  cancel(): void {
    this.dialogRef.close(null);
  }

  confirm(): void {
    this.saving = true;
    const trimmed = this.reason.trim();
    this.api.post<any>(
      `/quotations/${this.data.quotationId}/${this.data.stage}/unlock-edit`,
      { reason: trimmed || null },
    ).subscribe({
      next: () => {
        this.notify.success(`${this.data.stageLabel} unlocked for editing.`);
        this.dialogRef.close(true);
      },
      error: (err) => {
        this.saving = false;
        this.notify.error(err?.error?.detail || 'Unlock failed.');
      },
    });
  }
}
