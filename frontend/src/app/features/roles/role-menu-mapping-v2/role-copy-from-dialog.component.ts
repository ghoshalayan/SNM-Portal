import { CommonModule } from '@angular/common';
import { Component, Inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatRadioModule } from '@angular/material/radio';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { MenuPermission } from './role-permission.types';

export interface CopyFromDialogData {
  currentRoleId: number;
  currentPermissions: MenuPermission[];
}

export interface CopyFromDialogResult {
  sourceRoleId: number;
  permissions: MenuPermission[];
  includeFlags: boolean;
}

interface RoleOption {
  roleId: number;
  roleName: string;
}

@Component({
  selector: 'app-role-copy-from-dialog',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatDialogModule, MatButtonModule,
    MatCheckboxModule, MatIconModule, MatProgressSpinnerModule, MatRadioModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon>content_copy</mat-icon>
      Copy permissions from…
    </h2>

    <mat-dialog-content>
      @if (loading) {
        <div class="cfd-loading"><mat-spinner diameter="32"></mat-spinner></div>
      } @else {
        <p class="cfd-hint">
          Pick a source role. Its permissions will replace the current ones
          (you'll still need to press Save — this just fills the editor).
        </p>
        <mat-radio-group [(ngModel)]="sourceRoleId" class="cfd-radios">
          @for (r of roles; track r.roleId) {
            <mat-radio-button [value]="r.roleId" [disabled]="r.roleId === data.currentRoleId">
              {{ r.roleName }}
              @if (r.roleId === data.currentRoleId) { <em>(this role)</em> }
            </mat-radio-button>
          }
        </mat-radio-group>

        @if (previewDiff) {
          <div class="cfd-diff">
            <strong>Preview</strong>
            <ul>
              <li>{{ previewDiff.added }} new flags granted</li>
              <li>{{ previewDiff.removed }} existing flags removed</li>
              <li>{{ previewDiff.unchanged }} unchanged</li>
            </ul>
          </div>
        }
      }
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-stroked-button (click)="loadPreview()"
        [disabled]="!sourceRoleId || loadingPreview">
        <mat-icon>preview</mat-icon>
        {{ loadingPreview ? 'Loading…' : 'Preview diff' }}
      </button>
      <button mat-raised-button color="primary"
        [disabled]="!previewResult"
        (click)="apply()">
        <mat-icon>done</mat-icon> Apply
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    h2 { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; }
    .cfd-hint { font-size: 13px; color: var(--snm-text-muted); margin: 0 0 12px; }
    .cfd-loading { display: flex; justify-content: center; padding: 24px; }
    .cfd-radios { display: flex; flex-direction: column; gap: 6px; }
    .cfd-radios mat-radio-button em { font-style: italic; color: var(--snm-text-muted); margin-left: 6px; font-size: 12px; }
    .cfd-diff {
      margin-top: 14px;
      padding: 10px 12px;
      background: var(--snm-accent-subtle);
      border-radius: 8px;
      font-size: 13px;
    }
    .cfd-diff strong {
      display: block;
      margin-bottom: 4px;
      color: var(--snm-accent-dark);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .cfd-diff ul { margin: 0; padding-left: 16px; }
  `],
})
export class RoleCopyFromDialogComponent implements OnInit {
  loading = true;
  loadingPreview = false;
  roles: RoleOption[] = [];
  sourceRoleId: number | null = null;

  previewResult: MenuPermission[] | null = null;
  previewDiff: { added: number; removed: number; unchanged: number } | null = null;

  constructor(
    public dialogRef: MatDialogRef<RoleCopyFromDialogComponent, CopyFromDialogResult>,
    @Inject(MAT_DIALOG_DATA) public data: CopyFromDialogData,
    private api: ApiService,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    this.api.get<RoleOption[]>('/roles').subscribe({
      next: (rs) => { this.roles = rs || []; this.loading = false; },
      error: () => { this.loading = false; this.notify.error('Failed to load roles'); },
    });
  }

  loadPreview(): void {
    if (!this.sourceRoleId) return;
    this.loadingPreview = true;
    this.api.get<MenuPermission[]>(`/menus/role-menu-map/${this.sourceRoleId}`).subscribe({
      next: (perms) => {
        this.previewResult = perms;
        this.previewDiff = this.diff(this.data.currentPermissions, perms);
        this.loadingPreview = false;
      },
      error: () => {
        this.loadingPreview = false;
        this.notify.error('Failed to load source role permissions');
      },
    });
  }

  apply(): void {
    if (!this.previewResult || !this.sourceRoleId) return;
    this.dialogRef.close({
      sourceRoleId: this.sourceRoleId,
      permissions: this.previewResult,
      includeFlags: false,  // Settings-flag copying is a future enhancement.
    });
  }

  private diff(before: MenuPermission[], after: MenuPermission[]) {
    const byMenu = new Map(before.map(p => [p.menuId, p]));
    const flags = [
      'canAdd', 'canRead', 'canEdit', 'canDelete', 'canEditNumber',
      'canApprove', 'canRevise', 'canTransferOwnership', 'canGenerateUnderOthers',
    ];
    let added = 0, removed = 0, unchanged = 0;
    for (const a of after) {
      const b = byMenu.get(a.menuId);
      for (const f of flags) {
        const aVal = !!(a as any)[f];
        const bVal = !!(b as any)?.[f];
        if (aVal && !bVal) added++;
        else if (!aVal && bVal) removed++;
        else unchanged++;
      }
    }
    return { added, removed, unchanged };
  }
}
