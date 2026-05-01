import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  Inject,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatTabsModule } from '@angular/material/tabs';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { Subject, debounceTime } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiService } from '../../../../core/services/api.service';
import { NotificationService } from '../../../../core/services/notification.service';
import { DashboardService } from '../../services/dashboard.service';
import { DashboardAssignment } from '../../models/schema.types';

interface RoleRow { roleId: number; roleName: string; }
interface UserSearchHit { id: number; label: string; sub?: string | null; }
interface UserSearchResponse { items: UserSearchHit[]; }

export interface ManageAssigneesDialogData {
  dashboardId: number;
  dashboardName: string;
}

@Component({
  selector: 'app-manage-assignees-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule, MatDialogModule,
    MatButtonModule, MatIconModule, MatFormFieldModule, MatInputModule,
    MatSelectModule, MatChipsModule, MatProgressSpinnerModule,
    MatTooltipModule, MatTabsModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="icon">group</mat-icon>
      Assignees · <span class="dash-name">{{ data.dashboardName }}</span>
    </h2>

    <mat-dialog-content>
      <p class="hint">
        Anyone listed below can see this dashboard, on top of the existing
        scope rules. SuperAdmins always see everything regardless.
      </p>

      <!-- Current assignees -->
      <section class="current">
        <div class="section-head">
          <h3>Current ({{ assignments().length }})</h3>
          <mat-spinner *ngIf="loading()" diameter="18"></mat-spinner>
        </div>
        <div class="chips" *ngIf="assignments().length; else noneTpl">
          <mat-chip *ngFor="let a of assignments(); trackBy: trackAssignment"
                    [matTooltip]="grantedTooltip(a)">
            <mat-icon class="chip-icon">{{ a.role_id ? 'workspace_premium' : 'person' }}</mat-icon>
            {{ a.role_id ? roleName(a.role_id) : userLabel(a.user_id!) }}
            <button matChipRemove [disabled]="busy()" (click)="revoke(a)">
              <mat-icon>close</mat-icon>
            </button>
          </mat-chip>
        </div>
        <ng-template #noneTpl>
          <p class="empty">No assignments yet — add a role or user below.</p>
        </ng-template>
      </section>

      <mat-tab-group class="tabs">
        <mat-tab label="Add role">
          <div class="picker">
            <mat-form-field appearance="outline" class="full">
              <mat-label>Role</mat-label>
              <mat-select [value]="selectedRoleId()" (valueChange)="selectedRoleId.set($event)">
                <mat-option *ngFor="let r of availableRoles()" [value]="r.roleId">
                  {{ r.roleName }}
                </mat-option>
                <mat-option *ngIf="!availableRoles().length" [value]="null" disabled>
                  All roles already assigned.
                </mat-option>
              </mat-select>
            </mat-form-field>
            <button mat-flat-button color="primary"
                    [disabled]="selectedRoleId() == null || busy()"
                    (click)="addRole()">
              <mat-icon>add</mat-icon>
              Grant
            </button>
          </div>
        </mat-tab>

        <mat-tab label="Add user">
          <div class="picker">
            <mat-form-field appearance="outline" class="full">
              <mat-label>Search user (name, login, code)</mat-label>
              <input matInput type="search"
                     [ngModel]="userSearch()"
                     (ngModelChange)="onUserSearch($event)">
              <mat-spinner *ngIf="searching()" matSuffix diameter="16"></mat-spinner>
            </mat-form-field>

            <div class="user-results" *ngIf="userResults().length">
              <button *ngFor="let u of userResults()"
                      class="user-row"
                      [disabled]="busy() || isUserAssigned(u.id)"
                      (click)="addUser(u)">
                <span class="u-label">{{ u.label }}</span>
                <span class="u-sub" *ngIf="u.sub">· {{ u.sub }}</span>
                <span class="u-already" *ngIf="isUserAssigned(u.id)">already assigned</span>
              </button>
            </div>
            <p *ngIf="!userResults().length && userSearch().trim() && !searching()"
               class="empty">No users match.</p>
          </div>
        </mat-tab>
      </mat-tab-group>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-flat-button [mat-dialog-close]="changed()">Done</button>
    </mat-dialog-actions>
  `,
  styles: [`
    h2 mat-dialog-title { display: flex; align-items: center; gap: 8px; }
    .icon { color: var(--snm-accent); }
    .dash-name { color: var(--snm-text-muted); font-weight: 400; }
    .hint { color: var(--snm-text-muted); font-size: 0.85rem; margin: 0 0 12px; }

    .current { margin-bottom: 16px; }
    .section-head {
      display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
      h3 { margin: 0; font-size: 0.95rem; color: var(--snm-text-secondary); }
    }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip-icon { font-size: 16px; width: 16px; height: 16px; margin-right: 4px; }
    .empty { color: var(--snm-text-muted); font-style: italic; padding: 8px 0; }

    .tabs { margin-top: 8px; }
    .picker {
      display: flex; gap: 8px; align-items: flex-start;
      padding: 16px 4px 8px;
    }
    .picker .full { flex: 1; }
    .picker button { margin-top: 6px; }

    .user-results {
      display: flex; flex-direction: column; gap: 4px;
      max-height: 240px; overflow-y: auto;
      padding: 0 4px;
    }
    .user-row {
      display: flex; gap: 8px; align-items: center;
      padding: 8px 12px; border-radius: 4px;
      background: transparent; border: 1px solid var(--snm-border-divider, #eee);
      cursor: pointer; text-align: left;
    }
    .user-row:hover:not([disabled]) {
      background: var(--snm-bg-panel, #f5f5f5);
      border-color: var(--snm-accent);
    }
    .user-row[disabled] { opacity: 0.6; cursor: not-allowed; }
    .u-label { font-weight: 500; }
    .u-sub { color: var(--snm-text-muted); font-size: 0.85rem; }
    .u-already {
      margin-left: auto;
      font-size: 0.7rem;
      color: var(--snm-text-muted);
      font-style: italic;
    }
  `],
})
export class ManageAssigneesDialogComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dashboards = inject(DashboardService);
  private readonly notify = inject(NotificationService);
  private readonly destroyRef = inject(DestroyRef);

  // ---- state ------------------------------------------------------------
  readonly assignments = signal<DashboardAssignment[]>([]);
  readonly roles = signal<RoleRow[]>([]);
  readonly userResults = signal<UserSearchHit[]>([]);
  readonly userSearch = signal('');
  readonly selectedRoleId = signal<number | null>(null);
  /** Cache of {userId → label} for displaying assigned users without
   * a separate fetch round-trip. Populated as we encounter them. */
  readonly userLookup = signal<Record<number, string>>({});

  readonly loading = signal(false);
  readonly searching = signal(false);
  readonly busy = signal(false);
  /** True once any add/revoke succeeded. Returned via dialog close so the
   * caller can refresh whatever cached count it shows. */
  readonly changed = signal(false);

  // ---- derived ----------------------------------------------------------
  readonly availableRoles = computed(() => {
    const assignedRoleIds = new Set(
      this.assignments().filter(a => a.role_id != null).map(a => a.role_id!),
    );
    return this.roles().filter(r => !assignedRoleIds.has(r.roleId));
  });

  private readonly searchSubject = new Subject<string>();

  constructor(
    private readonly ref: MatDialogRef<ManageAssigneesDialogComponent, boolean>,
    @Inject(MAT_DIALOG_DATA) public data: ManageAssigneesDialogData,
  ) {}

  ngOnInit(): void {
    // Debounced user search so we don't flood the backend while the user types.
    this.searchSubject
      .pipe(debounceTime(300), takeUntilDestroyed(this.destroyRef))
      .subscribe(q => this.runUserSearch(q));

    this.loadAssignments();
    this.loadRoles();
  }

  // ---- loaders ----------------------------------------------------------

  private loadAssignments(): void {
    this.loading.set(true);
    this.dashboards.listAssignments(this.data.dashboardId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: list => {
          this.assignments.set(list);
          this.loading.set(false);
          // Pre-warm the user lookup for any user_id grants we don't
          // already have a label for.
          const missing = list
            .map(a => a.user_id)
            .filter((id): id is number => id != null && !this.userLookup()[id]);
          missing.forEach(id => this.fetchUserLabel(id));
        },
        error: err => {
          this.loading.set(false);
          this.notify.error(err?.error?.detail ?? 'Failed to load assignments');
        },
      });
  }

  private loadRoles(): void {
    // /api/v1/roles is gated to logged-in users + scoped to their company.
    // SuperAdmin sees all roles for that company without extra params.
    this.api.get<RoleRow[]>('/roles')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: rows => this.roles.set(rows ?? []),
        error: () => this.roles.set([]),
      });
  }

  private fetchUserLabel(userId: number): void {
    this.api.get<{ userId: number; userName: string; userLogin: string }>(`/users/${userId}`)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: u => this.userLookup.update(m => ({ ...m, [userId]: u.userName || u.userLogin })),
        error: () => this.userLookup.update(m => ({ ...m, [userId]: `User #${userId}` })),
      });
  }

  // ---- search -----------------------------------------------------------

  onUserSearch(v: string): void {
    this.userSearch.set(v);
    this.searchSubject.next(v);
  }

  private runUserSearch(q: string): void {
    const trimmed = (q || '').trim();
    if (!trimmed) { this.userResults.set([]); return; }
    this.searching.set(true);
    this.api.get<UserSearchResponse>('/users/search', { search: trimmed, limit: 20 })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.userResults.set(res?.items ?? []);
          // Cache labels for each hit — used both in the chip list and
          // for "already assigned" detection.
          const updates: Record<number, string> = {};
          (res?.items ?? []).forEach(u => { updates[u.id] = u.label; });
          if (Object.keys(updates).length) {
            this.userLookup.update(m => ({ ...m, ...updates }));
          }
          this.searching.set(false);
        },
        error: () => { this.userResults.set([]); this.searching.set(false); },
      });
  }

  // ---- mutations --------------------------------------------------------

  addRole(): void {
    const rid = this.selectedRoleId();
    if (rid == null) return;
    this.busy.set(true);
    this.dashboards.addAssignment(this.data.dashboardId, { role_id: rid })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: row => {
          // De-dupe: backend may return an existing row instead of a new one.
          this.assignments.update(list => {
            if (list.some(a => a.assignment_id === row.assignment_id)) return list;
            return [...list, row];
          });
          this.selectedRoleId.set(null);
          this.changed.set(true);
          this.busy.set(false);
        },
        error: err => {
          this.busy.set(false);
          this.notify.error(err?.error?.detail?.message ?? err?.error?.detail ?? 'Grant failed');
        },
      });
  }

  addUser(u: UserSearchHit): void {
    if (this.isUserAssigned(u.id)) return;
    this.busy.set(true);
    this.dashboards.addAssignment(this.data.dashboardId, { user_id: u.id })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: row => {
          this.assignments.update(list => {
            if (list.some(a => a.assignment_id === row.assignment_id)) return list;
            return [...list, row];
          });
          this.userLookup.update(m => ({ ...m, [u.id]: u.label }));
          this.changed.set(true);
          this.busy.set(false);
        },
        error: err => {
          this.busy.set(false);
          this.notify.error(err?.error?.detail?.message ?? err?.error?.detail ?? 'Grant failed');
        },
      });
  }

  revoke(a: DashboardAssignment): void {
    this.busy.set(true);
    this.dashboards.revokeAssignment(this.data.dashboardId, a.assignment_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.assignments.update(list =>
            list.filter(x => x.assignment_id !== a.assignment_id),
          );
          this.changed.set(true);
          this.busy.set(false);
        },
        error: err => {
          this.busy.set(false);
          this.notify.error(err?.error?.detail?.message ?? err?.error?.detail ?? 'Revoke failed');
        },
      });
  }

  // ---- view helpers -----------------------------------------------------

  roleName(roleId: number): string {
    return this.roles().find(r => r.roleId === roleId)?.roleName ?? `Role #${roleId}`;
  }

  userLabel(userId: number): string {
    return this.userLookup()[userId] ?? `User #${userId}`;
  }

  isUserAssigned(userId: number): boolean {
    return this.assignments().some(a => a.user_id === userId);
  }

  grantedTooltip(a: DashboardAssignment): string {
    const date = new Date(a.granted_at).toLocaleString();
    const by = a.granted_by != null ? ` by user #${a.granted_by}` : '';
    return `Granted ${date}${by}`;
  }

  trackAssignment = (_: number, a: DashboardAssignment) => a.assignment_id;
}
