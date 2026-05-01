import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatDividerModule } from '@angular/material/divider';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';

export interface ProfileDialogData {
  userId: number;
  userName: string;
  companyName: string;
  roleName: string;
  isSuperAdmin: boolean;
}

@Component({
  selector: 'app-profile-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatDividerModule,
  ],
  template: `
    <div class="profile-dialog">
      <div class="profile-header">
        <div class="avatar-large">{{ initial }}</div>
        <h2>{{ data.userName }}</h2>
      </div>

      <mat-divider></mat-divider>

      <div class="profile-details">
        <div class="detail-row">
          <mat-icon>business</mat-icon>
          <div>
            <span class="detail-label">Company</span>
            <span class="detail-value">{{ data.companyName }}</span>
          </div>
        </div>
        <div class="detail-row">
          <mat-icon>badge</mat-icon>
          <div>
            <span class="detail-label">Role</span>
            <span class="detail-value">{{ data.roleName }}</span>
          </div>
        </div>
        @if (data.isSuperAdmin) {
          <div class="detail-row">
            <mat-icon>shield</mat-icon>
            <div>
              <span class="detail-label">Access</span>
              <span class="detail-value super-admin">Super Admin</span>
            </div>
          </div>
        }
      </div>

      <mat-divider></mat-divider>

      <!-- Change Password Section -->
      <div class="change-password-section">
        <button mat-stroked-button color="primary" (click)="showPasswordForm = !showPasswordForm" class="toggle-password-btn">
          <mat-icon>lock</mat-icon>
          {{ showPasswordForm ? 'Cancel' : 'Change Password' }}
        </button>

        @if (showPasswordForm) {
          <div class="password-form">
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Current Password</mat-label>
              <input matInput [type]="hideCurrentPw ? 'password' : 'text'" [(ngModel)]="currentPassword" />
              <button mat-icon-button matSuffix (click)="hideCurrentPw = !hideCurrentPw" type="button">
                <mat-icon>{{ hideCurrentPw ? 'visibility_off' : 'visibility' }}</mat-icon>
              </button>
            </mat-form-field>

            <mat-form-field appearance="outline" class="full-width">
              <mat-label>New Password</mat-label>
              <input matInput [type]="hideNewPw ? 'password' : 'text'" [(ngModel)]="newPassword" />
              <button mat-icon-button matSuffix (click)="hideNewPw = !hideNewPw" type="button">
                <mat-icon>{{ hideNewPw ? 'visibility_off' : 'visibility' }}</mat-icon>
              </button>
            </mat-form-field>

            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Confirm New Password</mat-label>
              <input matInput [type]="hideConfirmPw ? 'password' : 'text'" [(ngModel)]="confirmPassword" />
              <button mat-icon-button matSuffix (click)="hideConfirmPw = !hideConfirmPw" type="button">
                <mat-icon>{{ hideConfirmPw ? 'visibility_off' : 'visibility' }}</mat-icon>
              </button>
            </mat-form-field>

            @if (passwordError) {
              <p class="error-text">{{ passwordError }}</p>
            }

            <button mat-raised-button color="primary" (click)="changePassword()" [disabled]="saving" class="save-password-btn">
              @if (saving) {
                Saving...
              } @else {
                Update Password
              }
            </button>
          </div>
        }
      </div>

      <div class="dialog-actions">
        <button mat-button (click)="dialogRef.close()">Close</button>
      </div>
    </div>
  `,
  styles: [`
    .profile-dialog {
      min-width: 360px;
    }

    .profile-header {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 24px 24px 16px;
    }

    .avatar-large {
      width: 72px;
      height: 72px;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--snm-avatar-gradient-start), var(--snm-avatar-gradient-end));
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 28px;
      font-weight: 600;
      margin-bottom: 12px;
      box-shadow: 0 4px 16px var(--snm-avatar-shadow);
    }

    .profile-header h2 {
      margin: 0;
      font-size: 20px;
      font-weight: 600;
      color: var(--snm-text-primary);
    }

    .profile-details {
      padding: 16px 24px;
    }

    .detail-row {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 0;

      mat-icon {
        color: var(--snm-accent-dark);
        font-size: 20px;
        width: 20px;
        height: 20px;
      }

      div {
        display: flex;
        flex-direction: column;
      }

      .detail-label {
        font-size: 11px;
        color: var(--snm-text-muted);
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }

      .detail-value {
        font-size: 14px;
        font-weight: 500;
        color: var(--snm-text-primary);
      }

      .super-admin {
        color: var(--snm-super-admin);
        font-weight: 600;
      }
    }

    .change-password-section {
      padding: 16px 24px;
    }

    .toggle-password-btn {
      width: 100%;
    }

    .password-form {
      margin-top: 16px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .full-width {
      width: 100%;
    }

    .error-text {
      color: var(--snm-error);
      font-size: 12px;
      margin: -4px 0 8px;
    }

    .save-password-btn {
      width: 100%;
    }

    .dialog-actions {
      display: flex;
      justify-content: flex-end;
      padding: 8px 16px 16px;
    }
  `],
})
export class ProfileDialogComponent {
  initial: string;
  showPasswordForm = false;
  currentPassword = '';
  newPassword = '';
  confirmPassword = '';
  passwordError = '';
  saving = false;

  hideCurrentPw = true;
  hideNewPw = true;
  hideConfirmPw = true;

  constructor(
    public dialogRef: MatDialogRef<ProfileDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: ProfileDialogData,
    private api: ApiService,
    private notify: NotificationService,
  ) {
    this.initial = (data.userName?.charAt(0) || 'U').toUpperCase();
  }

  changePassword(): void {
    this.passwordError = '';

    if (!this.currentPassword || !this.newPassword || !this.confirmPassword) {
      this.passwordError = 'All fields are required.';
      return;
    }
    if (this.newPassword.length < 6) {
      this.passwordError = 'New password must be at least 6 characters.';
      return;
    }
    if (this.newPassword !== this.confirmPassword) {
      this.passwordError = 'New passwords do not match.';
      return;
    }

    this.saving = true;
    this.api.post('/auth/change-password', {
      currentPassword: this.currentPassword,
      newPassword: this.newPassword,
    }).subscribe({
      next: () => {
        this.notify.success('Password changed successfully');
        this.showPasswordForm = false;
        this.currentPassword = '';
        this.newPassword = '';
        this.confirmPassword = '';
        this.saving = false;
      },
      error: (e: any) => {
        const detail = e?.error?.detail || 'Failed to change password.';
        this.passwordError = detail;
        this.notify.error(detail);
        this.saving = false;
      },
    });
  }
}
