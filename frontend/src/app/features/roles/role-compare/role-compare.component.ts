import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';

import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import {
  ALL_PERMISSION_FLAGS,
  MenuPermission,
  PermissionSchema,
} from '../role-menu-mapping-v2/role-permission.types';

interface RoleOption {
  roleId: number;
  roleName: string;
}

interface DiffRow {
  menuId: number;
  menuName: string;
  parentMenuId: number | null;
  a: Record<string, boolean>;
  b: Record<string, boolean>;
  different: boolean;
}

/**
 * Side-by-side role comparison. Pick two roles, see exactly which flags
 * differ. Useful for "why can HOD-A do X but HOD-B can't?".
 *
 * Standalone route — doesn't interact with the v2 editor state. All edits
 * still happen on the per-role page.
 */
@Component({
  selector: 'app-role-compare',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    MatButtonModule, MatCardModule, MatFormFieldModule, MatIconModule,
    MatProgressSpinnerModule, MatSelectModule, MatTooltipModule,
  ],
  template: `
    <div class="rc-page">
      <div class="rc-top">
        <button mat-icon-button (click)="router.navigate(['/roles'])" matTooltip="Back">
          <mat-icon>arrow_back</mat-icon>
        </button>
        <h2>Compare Roles</h2>
        <span class="rc-spacer"></span>
        <label class="rc-toggle" matTooltip="Show only rows where the two roles differ">
          <input type="checkbox" [(ngModel)]="onlyDifferences" />
          Show differences only
        </label>
      </div>

      <div class="rc-pickers">
        <mat-form-field appearance="outline">
          <mat-label>Role A</mat-label>
          <mat-select [(ngModel)]="roleAId" (ngModelChange)="loadRoles()">
            @for (r of allRoles; track r.roleId) {
              <mat-option [value]="r.roleId" [disabled]="r.roleId === roleBId">{{ r.roleName }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-icon class="rc-vs">compare_arrows</mat-icon>
        <mat-form-field appearance="outline">
          <mat-label>Role B</mat-label>
          <mat-select [(ngModel)]="roleBId" (ngModelChange)="loadRoles()">
            @for (r of allRoles; track r.roleId) {
              <mat-option [value]="r.roleId" [disabled]="r.roleId === roleAId">{{ r.roleName }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
      </div>

      @if (loading) {
        <div class="rc-loading"><mat-spinner diameter="36"></mat-spinner></div>
      } @else if (!roleAId || !roleBId) {
        <div class="rc-empty">
          <mat-icon>compare</mat-icon>
          <p>Pick two roles to see their differences.</p>
        </div>
      } @else {
        <div class="rc-summary">
          <strong>{{ diffCount }}</strong> flag
          {{ diffCount === 1 ? 'differs' : 'differ' }} between
          <span class="role-a">{{ nameFor(roleAId) }}</span>
          and
          <span class="role-b">{{ nameFor(roleBId) }}</span>.
        </div>

        <div class="rc-table-wrap">
          <table class="rc-table">
            <thead>
              <tr>
                <th rowspan="2" class="col-menu">Menu</th>
                @for (f of allFlags; track f) {
                  <th colspan="2" class="col-flag-group">{{ labelFor(f) }}</th>
                }
              </tr>
              <tr>
                @for (f of allFlags; track f) {
                  <th class="col-sub">A</th>
                  <th class="col-sub">B</th>
                }
              </tr>
            </thead>
            <tbody>
              @for (row of visibleRows; track row.menuId) {
                <tr [class.different]="row.different">
                  <td class="col-menu">{{ row.menuName }}</td>
                  @for (f of allFlags; track f) {
                    <td class="col-cell" [class.diff-a]="row.different && row.a[f] !== row.b[f] && row.a[f]">
                      <mat-icon class="tick" [class.on]="row.a[f]">{{ row.a[f] ? 'check' : 'close' }}</mat-icon>
                    </td>
                    <td class="col-cell" [class.diff-b]="row.different && row.a[f] !== row.b[f] && row.b[f]">
                      <mat-icon class="tick" [class.on]="row.b[f]">{{ row.b[f] ? 'check' : 'close' }}</mat-icon>
                    </td>
                  }
                </tr>
              }
              @if (visibleRows.length === 0) {
                <tr><td [attr.colspan]="1 + allFlags.length * 2" class="rc-muted">
                  No differences. The two roles have identical permissions.
                </td></tr>
              }
            </tbody>
          </table>
        </div>
      }
    </div>
  `,
  styles: [`
    .rc-page { padding: 20px 24px; max-width: 1400px; margin: 0 auto; }
    .rc-top { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
    .rc-top h2 { margin: 0; font-size: 20px; font-weight: 600; }
    .rc-spacer { flex: 1; }
    .rc-toggle { display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer; }

    .rc-pickers {
      display: flex; align-items: center; gap: 16px;
      margin-bottom: 16px;
    }
    .rc-pickers mat-form-field { flex: 1; max-width: 280px; }
    .rc-vs { color: var(--snm-accent-dark); font-size: 28px; width: 28px; height: 28px; margin-top: -18px; }

    .rc-loading { display: flex; justify-content: center; padding: 40px; }
    .rc-empty {
      text-align: center; padding: 64px 20px; color: var(--snm-text-muted);
    }
    .rc-empty mat-icon { font-size: 48px; width: 48px; height: 48px; opacity: 0.5; }
    .rc-empty p { margin: 12px 0 0; font-size: 14px; }

    .rc-summary {
      font-size: 14px;
      margin: 12px 0;
      padding: 10px 14px;
      border-left: 3px solid var(--snm-accent);
      background: var(--snm-accent-subtle);
      border-radius: 6px;
    }
    .rc-summary strong { color: var(--snm-accent-dark); font-size: 18px; margin-right: 4px; }
    .rc-summary .role-a { font-weight: 700; color: #1565c0; }
    .rc-summary .role-b { font-weight: 700; color: #e65100; }

    .rc-table-wrap { overflow-x: auto; border: 1px solid var(--snm-border-divider); border-radius: 8px; }
    .rc-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .rc-table th, .rc-table td {
      border: 1px solid var(--snm-border-divider);
      padding: 4px 6px;
      text-align: center;
    }
    .rc-table th {
      background: var(--snm-bg-header-row);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.3px;
      color: var(--snm-text-secondary);
      font-size: 11px;
    }
    .rc-table .col-menu {
      text-align: left; min-width: 180px;
      position: sticky; left: 0; background: var(--snm-sticky-bg);
      z-index: 1;
    }
    .rc-table .col-flag-group { min-width: 80px; }
    .rc-table .col-sub { font-size: 10px; color: var(--snm-text-muted); }
    .rc-table .col-cell { min-width: 34px; }
    .rc-table tr.different { background: rgba(230, 81, 0, 0.06); }
    .rc-table td.diff-a {
      background: rgba(21, 101, 192, 0.18);
    }
    .rc-table td.diff-b {
      background: rgba(230, 81, 0, 0.18);
    }
    .tick { font-size: 16px; width: 16px; height: 16px; color: var(--snm-text-faint); vertical-align: middle; }
    .tick.on { color: #2e7d32; }
    .rc-muted { color: var(--snm-text-muted); padding: 20px !important; }
  `],
})
export class RoleCompareComponent implements OnInit {
  allRoles: RoleOption[] = [];
  roleAId: number | null = null;
  roleBId: number | null = null;
  onlyDifferences = true;

  loading = false;
  schema: PermissionSchema | null = null;
  private aPerms: MenuPermission[] = [];
  private bPerms: MenuPermission[] = [];
  rows: DiffRow[] = [];

  get allFlags(): string[] { return [...ALL_PERMISSION_FLAGS] as string[]; }
  get visibleRows(): DiffRow[] {
    return this.onlyDifferences ? this.rows.filter(r => r.different) : this.rows;
  }
  get diffCount(): number {
    return this.rows.reduce((sum, r) => {
      return sum + this.allFlags.filter(f => !!r.a[f] !== !!r.b[f]).length;
    }, 0);
  }

  constructor(
    public router: Router,
    private route: ActivatedRoute,
    private api: ApiService,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    forkJoin({
      roles: this.api.get<RoleOption[]>('/roles'),
      schema: this.api.get<PermissionSchema>('/menus/permission-schema'),
    }).subscribe({
      next: ({ roles, schema }) => {
        this.allRoles = roles || [];
        this.schema = schema;
        const a = Number(this.route.snapshot.queryParams['a']);
        const b = Number(this.route.snapshot.queryParams['b']);
        if (a) this.roleAId = a;
        if (b) this.roleBId = b;
        if (a && b) this.loadRoles();
      },
      error: () => this.notify.error('Failed to load roles'),
    });
  }

  loadRoles(): void {
    if (!this.roleAId || !this.roleBId) {
      this.rows = [];
      return;
    }
    this.loading = true;
    forkJoin({
      a: this.api.get<MenuPermission[]>(`/menus/role-menu-map/${this.roleAId}`).pipe(catchError(() => of([] as MenuPermission[]))),
      b: this.api.get<MenuPermission[]>(`/menus/role-menu-map/${this.roleBId}`).pipe(catchError(() => of([] as MenuPermission[]))),
    }).subscribe({
      next: ({ a, b }) => {
        this.aPerms = a;
        this.bPerms = b;
        this.rows = this.buildDiff(a, b);
        this.loading = false;
      },
      error: () => { this.loading = false; this.notify.error('Failed to load permissions'); },
    });
  }

  private buildDiff(a: MenuPermission[], b: MenuPermission[]): DiffRow[] {
    const byA = new Map(a.map(p => [p.menuId, p]));
    const byB = new Map(b.map(p => [p.menuId, p]));
    const allIds = new Set<number>([...byA.keys(), ...byB.keys()]);
    const nameFor = (p?: MenuPermission) => p?.menuName || '(unknown)';
    const rows: DiffRow[] = [];
    for (const id of allIds) {
      const pa = byA.get(id);
      const pb = byB.get(id);
      const aFlags: Record<string, boolean> = {};
      const bFlags: Record<string, boolean> = {};
      let different = false;
      for (const f of ALL_PERMISSION_FLAGS) {
        aFlags[f] = !!(pa as any)?.[f];
        bFlags[f] = !!(pb as any)?.[f];
        if (aFlags[f] !== bFlags[f]) different = true;
      }
      rows.push({
        menuId: id,
        menuName: nameFor(pa) !== '(unknown)' ? nameFor(pa) : nameFor(pb),
        parentMenuId: pa?.parentMenuId ?? pb?.parentMenuId ?? null,
        a: aFlags,
        b: bFlags,
        different,
      });
    }
    // Match the ordering used in the single-role editor
    rows.sort((x, y) => {
      const px = (byA.get(x.menuId) || byB.get(x.menuId))?.menuOrder ?? 0;
      const py = (byA.get(y.menuId) || byB.get(y.menuId))?.menuOrder ?? 0;
      return px - py;
    });
    return rows;
  }

  labelFor(flag: string): string {
    return this.schema?.labels?.[flag] || flag;
  }

  nameFor(roleId: number | null): string {
    if (!roleId) return '';
    return this.allRoles.find(r => r.roleId === roleId)?.roleName || `#${roleId}`;
  }
}
