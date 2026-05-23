import { CommonModule } from '@angular/common';
import { Component, DestroyRef, HostListener, inject, OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';

import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { RoleAuditPanelComponent } from './role-audit-panel.component';
import { RoleConflictCheckService } from './role-conflict-check.service';
import {
  CopyFromDialogData,
  CopyFromDialogResult,
  RoleCopyFromDialogComponent,
} from './role-copy-from-dialog.component';
import {
  ALL_PERMISSION_FLAGS,
  MenuPermission,
  PermissionConflict,
  PermissionSchema,
  RoleSettings,
} from './role-permission.types';
import { RolePermissionsMatrixComponent } from './role-permissions-matrix.component';
import { RolePreviewStripComponent } from './role-preview-strip.component';
import { RoleSettingsPanelComponent } from './role-settings-panel.component';

/**
 * v2 Role-Menu Permissions — tabbed shell.
 *
 * Tabs: Role Settings · Permissions Matrix · Audit History.
 * Handles dirty-state tracking, unsaved-changes guard, and wires the
 * sub-components together. Does NOT replace the existing page — the
 * classic UI is still reachable at /roles/:id/permissions.
 */
@Component({
  selector: 'app-role-menu-mapping-v2',
  standalone: true,
  imports: [
    CommonModule, RouterLink,
    MatButtonModule, MatCardModule, MatIconModule, MatProgressSpinnerModule,
    MatTabsModule, MatTooltipModule, MatDialogModule,
    RoleSettingsPanelComponent,
    RolePermissionsMatrixComponent,
    RolePreviewStripComponent,
    RoleAuditPanelComponent,
  ],
  template: `
    <div class="v2-page">
      <!-- Top bar -->
      <div class="v2-top">
        <button mat-icon-button (click)="goBack()" matTooltip="Back">
          <mat-icon>arrow_back</mat-icon>
        </button>
        <h2 class="v2-title">
          Role Permissions —
          <span class="role-name">{{ settings?.roleName || '…' }}</span>
        </h2>
        <span class="v2-spacer"></span>

        @if (dirty) {
          <span class="dirty-chip" matTooltip="Unsaved changes">
            <mat-icon>circle</mat-icon> Unsaved
          </span>
        } @else if (lastSavedMoment) {
          <span class="saved-chip">
            <mat-icon>check_circle</mat-icon> Saved {{ lastSavedMoment }}
          </span>
        }

        <button mat-stroked-button
          [routerLink]="['/roles', roleId, 'menu-mapping']"
          matTooltip="Open the classic permissions UI (kept around as a fallback)">
          <mat-icon>history</mat-icon> Classic UI
        </button>
        <button mat-stroked-button (click)="openCompare()" matTooltip="Compare roles side by side">
          <mat-icon>compare</mat-icon> Compare
        </button>
        <button mat-raised-button color="primary"
          (click)="save()"
          [disabled]="saving || loading || !dirty">
          @if (saving) { <mat-spinner diameter="18" class="inline-spinner"></mat-spinner> }
          <mat-icon *ngIf="!saving">save</mat-icon>
          {{ saving ? 'Saving…' : 'Save' }}
        </button>
      </div>

      @if (loading) {
        <div class="v2-loading">
          <mat-spinner diameter="40"></mat-spinner>
        </div>
      } @else {
        <!-- Always-visible preview strip -->
        <app-role-preview-strip [permissions]="flatPermissions"></app-role-preview-strip>

        <mat-tab-group [(selectedIndex)]="activeTab" animationDuration="200ms">
          <mat-tab label="Role Settings">
            <div class="v2-tab-body">
              @if (settings) {
                <app-role-settings-panel
                  [settings]="settings"
                  (settingsChange)="onSettingsChange($event)">
                </app-role-settings-panel>
              }
            </div>
          </mat-tab>

          <mat-tab label="Permissions Matrix">
            <div class="v2-tab-body">
              <app-role-permissions-matrix
                [flatPermissions]="flatPermissions"
                [schema]="schema"
                [conflicts]="conflicts"
                (permissionsChange)="onPermissionsChange($event)"
                (copyFromRole)="openCopyFrom()"
                (autoFix)="runAutoFix()">
              </app-role-permissions-matrix>
            </div>
          </mat-tab>

          <mat-tab label="Audit History">
            <div class="v2-tab-body">
              <app-role-audit-panel
                [roleId]="roleId"
                [active]="activeTab === 2">
              </app-role-audit-panel>
            </div>
          </mat-tab>
        </mat-tab-group>
      }
    </div>
  `,
  styles: [`
    .v2-page {
      padding: 20px 24px;
      max-width: 1200px;
      margin: 0 auto;
    }
    .v2-top {
      display: flex; align-items: center; gap: 10px;
      margin-bottom: 14px;
    }
    .v2-title {
      font-size: 20px;
      margin: 0;
      font-weight: 600;
      color: var(--snm-text-primary);
    }
    .v2-title .role-name { color: var(--snm-accent); font-weight: 700; }
    .v2-spacer { flex: 1; }
    .dirty-chip, .saved-chip {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 3px 10px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 600;
    }
    .dirty-chip {
      background: rgba(230, 81, 0, 0.12);
      color: #e65100;
      border: 1px solid rgba(230, 81, 0, 0.3);
    }
    .dirty-chip mat-icon {
      font-size: 10px; width: 10px; height: 10px;
      color: #e65100;
    }
    .saved-chip {
      background: rgba(46, 125, 50, 0.12);
      color: #2e7d32;
      border: 1px solid rgba(46, 125, 50, 0.3);
    }
    .saved-chip mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .inline-spinner { display: inline-block; margin-right: 8px; }

    .v2-loading { display: flex; justify-content: center; padding: 64px 0; }
    .v2-tab-body { padding: 16px 8px; }
  `],
})
export class RoleMenuMappingV2Component implements OnInit {
  roleId!: number;
  loading = true;
  saving = false;

  /** Active tab index (0 = settings, 1 = matrix, 2 = audit). */
  activeTab = 1;

  settings: RoleSettings | null = null;
  /** Deep-cloned from the last successful load. Used for dirty-state diff. */
  private pristineSettings: string = '';

  flatPermissions: MenuPermission[] = [];
  private pristinePermissions: string = '';

  schema: PermissionSchema | null = null;
  conflicts: PermissionConflict[] = [];

  lastSavedMoment: string | null = null;
  private destroyRef = inject(DestroyRef);

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: ApiService,
    private notify: NotificationService,
    private conflictSvc: RoleConflictCheckService,
    private dialog: MatDialog,
  ) {}

  ngOnInit(): void {
    this.roleId = +this.route.snapshot.params['roleId'];
    if (!this.roleId) {
      this.notify.error('Invalid role');
      this.router.navigate(['/roles']);
      return;
    }
    this.loadAll();
  }

  // ---- load ----
  private loadAll(): void {
    this.loading = true;
    forkJoin({
      role: this.api.get<any>(`/roles/${this.roleId}`),
      numGen: this.api.get<any>(`/roles/${this.roleId}/num-gen-mode`),
      perms: this.api.get<MenuPermission[]>(`/menus/role-menu-map/${this.roleId}`),
      schema: this.api.get<PermissionSchema>('/menus/permission-schema'),
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ role, numGen, perms, schema }) => {
          this.settings = {
            roleName: role.roleName,
            roleLevel: numGen.roleLevel ?? 0,
            numGenMode: numGen.numGenMode || 'own_code',
            peerAccess: numGen.peerAccess ?? false,
            peerSubtree: numGen.peerSubtree ?? false,
            locationScopeRequired: numGen.locationScopeRequired ?? true,
            canApproveTransfers: numGen.canApproveTransfers ?? false,
            isCompanyAdmin: numGen.IsCompanyAdmin ?? numGen.isCompanyAdmin ?? false,
            downwardLevels: numGen.downwardLevels ?? -1,
            upwardLevels: numGen.upwardLevels ?? 0,
            includeSubtreeOnUpward: numGen.includeSubtreeOnUpward ?? true,
            enforceChildLocationSubset: numGen.enforceChildLocationSubset ?? false,
          };
          this.flatPermissions = perms || [];
          this.schema = schema;
          this.pristineSettings = JSON.stringify(this.settings);
          this.pristinePermissions = JSON.stringify(this.flatPermissions);
          this.recomputeConflicts();
          this.loading = false;
        },
        error: () => {
          this.loading = false;
          this.notify.error('Failed to load role');
        },
      });
  }

  // ---- dirty state ----
  get dirty(): boolean {
    if (!this.settings) return false;
    return (
      JSON.stringify(this.settings) !== this.pristineSettings ||
      JSON.stringify(this.flatPermissions) !== this.pristinePermissions
    );
  }

  onSettingsChange(next: RoleSettings): void {
    this.settings = next;
  }

  onPermissionsChange(next: MenuPermission[]): void {
    this.flatPermissions = next;
    this.recomputeConflicts();
  }

  private recomputeConflicts(): void {
    this.conflicts = this.conflictSvc.check(this.flatPermissions);
  }

  runAutoFix(): void {
    this.conflictSvc.autoFix(this.flatPermissions, this.conflicts);
    this.flatPermissions = [...this.flatPermissions];
    this.recomputeConflicts();
    this.notify.success('Conflicts auto-fixed.');
  }

  // ---- save ----
  save(): void {
    if (!this.settings || this.saving) return;
    this.saving = true;

    // Schema-driven payload: forward *every* canXxx flag from the
    // loaded permission row. The backend's Pydantic schema accepts
    // them, the save handler iterates FIELD_TO_COL and writes the
    // ones it knows about, and unknown keys are rejected with 422
    // (loud failure at the API edge instead of silent unchecking).
    //
    // Why this matters: the previous hardcoded list silently dropped
    // any newly-added flag — user checks a box, save's POST omits it,
    // backend writes false, reload shows it unchecked. With this
    // passthrough, every flag the GET endpoint returns is round-
    // tripped automatically.
    const SKIP_KEYS = new Set<string>([
      'menuName', 'parentMenuId', 'menuOrder', 'children',
    ]);
    const permPayload = this.flatPermissions.map(p => {
      const out: Record<string, any> = { menuId: p.menuId };
      for (const key of Object.keys(p) as (keyof typeof p)[]) {
        if (key === 'menuId' || SKIP_KEYS.has(key as string)) continue;
        // Only flag-shape keys (canXxx) get coerced + forwarded;
        // anything else from the row is dropped to avoid sending
        // metadata the backend's `extra="forbid"` would reject.
        if (typeof key === 'string' && key.startsWith('can')) {
          out[key] = !!p[key];
        }
      }
      return out;
    });

    forkJoin({
      flags: this.api.put(`/roles/${this.roleId}/num-gen-mode`, {
        numGenMode: this.settings.numGenMode,
        peerAccess: this.settings.peerAccess,
        peerSubtree: this.settings.peerSubtree,
        roleLevel: this.settings.roleLevel,
        locationScopeRequired: this.settings.locationScopeRequired,
        canApproveTransfers: this.settings.canApproveTransfers,
        IsCompanyAdmin: this.settings.isCompanyAdmin,
        downwardLevels: this.settings.downwardLevels,
        upwardLevels: this.settings.upwardLevels,
        includeSubtreeOnUpward: this.settings.includeSubtreeOnUpward,
        enforceChildLocationSubset: this.settings.enforceChildLocationSubset,
      }),
      perms: this.api.post(`/menus/role-menu-map/${this.roleId}`, permPayload),
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.pristineSettings = JSON.stringify(this.settings);
          this.pristinePermissions = JSON.stringify(this.flatPermissions);
          this.saving = false;
          this.lastSavedMoment = 'just now';
          setTimeout(() => { if (this.lastSavedMoment === 'just now') this.lastSavedMoment = 'moments ago'; }, 2000);
          this.notify.success('Saved.');
        },
        error: () => {
          this.saving = false;
          this.notify.error('Save failed.');
        },
      });
  }

  // ---- navigation guards ----
  goBack(): void {
    if (this.dirty) {
      this.dialog.open(ConfirmDialogComponent, {
        data: {
          title: 'Unsaved changes',
          message: 'You have unsaved changes. Leave anyway?',
          confirmText: 'Leave',
          cancelText: 'Stay',
          confirmColor: 'warn',
        },
      }).afterClosed().subscribe(ok => {
        if (ok) this.router.navigate(['/roles']);
      });
    } else {
      this.router.navigate(['/roles']);
    }
  }

  openCompare(): void {
    this.router.navigate(['/roles/compare'], { queryParams: { a: this.roleId } });
  }

  openCopyFrom(): void {
    const ref = this.dialog.open<
      RoleCopyFromDialogComponent,
      CopyFromDialogData,
      CopyFromDialogResult
    >(RoleCopyFromDialogComponent, {
      data: { currentRoleId: this.roleId, currentPermissions: this.flatPermissions },
      width: '520px',
    });
    ref.afterClosed().subscribe((result) => {
      if (!result) return;
      // Replace flat permissions with the copied ones (retain menuId / menuName).
      // Source role may have menus the current company doesn't have; intersect
      // by menuId so we don't introduce phantom rows.
      const byMenu = new Map(this.flatPermissions.map(p => [p.menuId, p] as const));
      for (const copied of result.permissions) {
        const target = byMenu.get(copied.menuId);
        if (!target) continue;
        // Iterate ALL_PERMISSION_FLAGS so any flag added to the type
        // automatically participates in Copy-from. Prevents the
        // hardcoded-list silent-drop bug we previously had to fix
        // every time a new flag landed.
        for (const flag of ALL_PERMISSION_FLAGS) {
          (target as any)[flag] = !!(copied as any)[flag];
        }
      }
      this.flatPermissions = [...this.flatPermissions];
      this.recomputeConflicts();
      this.notify.success(`Permissions copied from source role. Press Save to commit.`);
    });
  }

  /** Browser-level navigate/refresh warning while dirty. */
  @HostListener('window:beforeunload', ['$event'])
  onBeforeUnload(e: BeforeUnloadEvent): void {
    if (this.dirty) {
      e.preventDefault();
      e.returnValue = '';
    }
  }
}
