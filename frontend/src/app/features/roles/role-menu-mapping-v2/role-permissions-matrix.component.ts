import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import {
  ALL_PERMISSION_FLAGS,
  FlagKey,
  MenuPermission,
  PermissionConflict,
  PermissionSchema,
  PRESETS,
} from './role-permission.types';

/**
 * Tab 2: permissions matrix.
 *
 * Features:
 *   - Recursive tree renderer (handles N-deep; no copy-paste per level)
 *   - Search filter (fades non-matching menus so tree structure stays intact)
 *   - Column bulk: "grant / clear Read|Add|Edit|Delete for all visible menus"
 *   - Collapsed extended section per row (expand on click, count chip shown)
 *   - Preset dropdown (Reader / Editor / Approver / Full / Clear)
 *   - Conflict warnings + auto-fix CTA
 */
@Component({
  selector: 'app-role-permissions-matrix',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    MatButtonModule, MatCheckboxModule, MatDividerModule, MatFormFieldModule,
    MatIconModule, MatInputModule, MatMenuModule, MatTooltipModule,
  ],
  template: `
    <div class="rpm">
      <!-- Top toolbar: search + bulk actions -->
      <div class="rpm-toolbar">
        <mat-form-field appearance="outline" class="rpm-search">
          <mat-label>Search menus…</mat-label>
          <mat-icon matPrefix>search</mat-icon>
          <input matInput [(ngModel)]="search" (ngModelChange)="onSearch()" />
          @if (search) {
            <button mat-icon-button matSuffix (click)="clearSearch()"><mat-icon>close</mat-icon></button>
          }
        </mat-form-field>

        <button mat-stroked-button [matMenuTriggerFor]="presetMenu">
          <mat-icon>auto_awesome</mat-icon> Preset
        </button>
        <mat-menu #presetMenu="matMenu">
          @for (p of presets; track p.id) {
            <button mat-menu-item (click)="applyPreset(p.id)">
              <div class="preset-item">
                <strong>{{ p.label }}</strong>
                <span class="preset-desc">{{ p.description }}</span>
              </div>
            </button>
          }
        </mat-menu>

        <button mat-stroked-button (click)="copyFromRole.emit()">
          <mat-icon>content_copy</mat-icon> Copy from role
        </button>

        <button mat-stroked-button [matMenuTriggerFor]="bulkMenu">
          <mat-icon>checklist</mat-icon> Bulk
        </button>
        <mat-menu #bulkMenu="matMenu">
          @for (f of coreFlags; track f) {
            <button mat-menu-item (click)="setColumnAll(f, true)">
              Grant <strong>{{ labelFor(f) }}</strong> on visible menus
            </button>
          }
          <mat-divider></mat-divider>
          @for (f of coreFlags; track f) {
            <button mat-menu-item (click)="setColumnAll(f, false)">
              Clear <strong>{{ labelFor(f) }}</strong> on visible menus
            </button>
          }
        </mat-menu>
      </div>

      <!-- Conflict banner -->
      @if (conflicts.length > 0) {
        <div class="rpm-conflicts">
          <mat-icon>warning</mat-icon>
          <div class="rpm-conflicts-body">
            <strong>{{ conflicts.length }} conflict{{ conflicts.length === 1 ? '' : 's' }} detected</strong>
            <ul>
              @for (c of conflicts.slice(0, 3); track c.menuId + ':' + c.kind) {
                <li>{{ c.message }}</li>
              }
              @if (conflicts.length > 3) {
                <li class="muted">+{{ conflicts.length - 3 }} more</li>
              }
            </ul>
          </div>
          <button mat-raised-button color="primary" (click)="autoFix.emit()">
            <mat-icon>auto_fix_high</mat-icon> Auto-fix
          </button>
        </div>
      }

      <!-- Matrix table -->
      <div class="rpm-table-wrap">
        <table class="rpm-table">
          <thead>
            <tr>
              <th class="col-menu">Menu</th>
              @for (f of coreFlags; track f) {
                <th class="col-flag">
                  <div class="th-stack">
                    <span>{{ labelFor(f) }}</span>
                    <mat-checkbox
                      [checked]="isColumnAllChecked(f)"
                      [indeterminate]="isColumnPartialChecked(f)"
                      (change)="setColumnAll(f, $event.checked)"
                      matTooltip="Toggle {{ labelFor(f) }} on all visible menus">
                    </mat-checkbox>
                  </div>
                </th>
              }
              <th class="col-ext" matTooltip="Extended perms (Approve, Revise, Transfer, Gen Under Others)">
                + Extended
              </th>
            </tr>
          </thead>
          <tbody>
            @for (node of tree; track node.menuId) {
              <ng-container *ngTemplateOutlet="row; context: { $implicit: node, depth: 0 }"></ng-container>
            }
          </tbody>
        </table>
      </div>

      <!-- Recursive row template (handles N levels; supersedes parent/child/grandchild copy-paste) -->
      <ng-template #row let-node let-depth="depth">
        <tr [class.dim]="!matchesSearch(node)"
            [class.has-conflict]="hasConflict(node.menuId)">
          <td class="col-menu" [style.padding-left.px]="12 + depth * 22">
            @if (node.children?.length) {
              <button mat-icon-button class="caret"
                (click)="toggleExpand(node.menuId)">
                <mat-icon>{{ isExpanded(node.menuId) ? 'expand_more' : 'chevron_right' }}</mat-icon>
              </button>
            } @else {
              <span class="caret-spacer"></span>
            }
            <span class="menu-label">{{ node.menuName }}</span>
            @if (hasConflict(node.menuId)) {
              <mat-icon class="conflict-dot" matTooltip="Has conflicts — see banner above">error_outline</mat-icon>
            }
          </td>
          @for (f of coreFlags; track f) {
            <td class="col-flag">
              <mat-checkbox
                [checked]="!!node[f]"
                (change)="toggle(node, f, $event.checked)">
              </mat-checkbox>
            </td>
          }
          <td class="col-ext">
            @if (extendedFor(node.menuName).length > 0) {
              <button mat-button class="ext-chip"
                (click)="toggleExtended(node.menuId)">
                {{ extendedCount(node) }} / {{ extendedFor(node.menuName).length }}
                <mat-icon>{{ isExtendedOpen(node.menuId) ? 'expand_less' : 'expand_more' }}</mat-icon>
              </button>
            } @else {
              <span class="muted">—</span>
            }
          </td>
        </tr>

        <!-- Inline extended perms drawer -->
        @if (isExtendedOpen(node.menuId) && extendedFor(node.menuName).length > 0) {
          <tr class="ext-drawer">
            <td [attr.colspan]="coreFlags.length + 2" [style.padding-left.px]="32 + depth * 22">
              <div class="ext-list">
                @for (ef of extendedFor(node.menuName); track ef) {
                  <mat-checkbox
                    [checked]="!!node[ef]"
                    (change)="toggle(node, ef, $event.checked)">
                    <strong>{{ labelFor(ef) }}</strong>
                    <span class="ext-desc">{{ descFor(ef) }}</span>
                  </mat-checkbox>
                }
              </div>
            </td>
          </tr>
        }

        <!-- Recurse into children -->
        @if (isExpanded(node.menuId) && node.children?.length) {
          @for (child of node.children; track child.menuId) {
            <ng-container *ngTemplateOutlet="row; context: { $implicit: child, depth: depth + 1 }"></ng-container>
          }
        }
      </ng-template>
    </div>
  `,
  styles: [`
    .rpm { display: flex; flex-direction: column; gap: 12px; }

    .rpm-toolbar {
      display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
      padding: 4px 0;
    }
    .rpm-search { flex: 1 1 280px; max-width: 420px; }
    .rpm-search .mat-mdc-form-field-subscript-wrapper { display: none; }

    .preset-item { display: flex; flex-direction: column; line-height: 1.2; }
    .preset-item .preset-desc {
      font-size: 11px; color: var(--snm-text-muted); font-weight: 400;
    }

    .rpm-conflicts {
      display: flex; gap: 10px; align-items: flex-start;
      padding: 10px 14px;
      background: rgba(230, 81, 0, 0.08);
      border: 1px solid rgba(230, 81, 0, 0.3);
      border-radius: 8px;
    }
    .rpm-conflicts > mat-icon {
      color: #e65100;
      flex-shrink: 0;
      margin-top: 2px;
    }
    .rpm-conflicts-body { flex: 1; font-size: 13px; color: var(--snm-text-primary); }
    .rpm-conflicts-body strong { display: block; margin-bottom: 4px; color: #e65100; }
    .rpm-conflicts-body ul { margin: 0; padding-left: 16px; }
    .rpm-conflicts-body .muted { color: var(--snm-text-muted); list-style: none; margin-left: -16px; }

    .rpm-table-wrap {
      overflow-x: auto;
      border: 1px solid var(--snm-border-divider);
      border-radius: 8px;
    }
    table.rpm-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .rpm-table th, .rpm-table td {
      border-bottom: 1px solid var(--snm-border-divider);
      padding: 6px 10px;
      vertical-align: middle;
    }
    .rpm-table th {
      background: var(--snm-bg-header-row);
      color: var(--snm-text-secondary);
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.3px;
      position: sticky; top: 0; z-index: 1;
    }
    .rpm-table .col-menu { min-width: 240px; }
    .rpm-table .col-flag { width: 80px; text-align: center; }
    .rpm-table .col-ext { width: 120px; text-align: center; }
    .th-stack { display: flex; flex-direction: column; align-items: center; gap: 2px; }

    tr.dim { opacity: 0.35; }
    tr.has-conflict { background: rgba(230, 81, 0, 0.04); }

    .caret {
      width: 26px; height: 26px; line-height: 26px;
      margin-right: 4px;
    }
    .caret mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .caret-spacer { display: inline-block; width: 30px; }

    .menu-label { vertical-align: middle; }
    .conflict-dot {
      font-size: 16px; width: 16px; height: 16px;
      color: #e65100;
      vertical-align: middle;
      margin-left: 6px;
    }

    .ext-chip {
      min-width: 0; padding: 2px 8px;
      font-size: 12px;
      color: var(--snm-accent-dark);
    }
    .ext-chip mat-icon {
      font-size: 16px; width: 16px; height: 16px; margin-left: 4px;
    }
    .ext-drawer td {
      background: rgba(91, 143, 217, 0.04);
      padding-top: 10px; padding-bottom: 10px;
    }
    .ext-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 6px 12px;
    }
    .ext-list mat-checkbox strong { font-size: 13px; }
    .ext-desc {
      display: block;
      font-size: 11px;
      color: var(--snm-text-muted);
      margin-top: 2px;
    }
    .muted { color: var(--snm-text-muted); }
  `],
})
export class RolePermissionsMatrixComponent implements OnChanges {
  @Input({ required: true }) flatPermissions: MenuPermission[] = [];
  @Input({ required: true }) schema: PermissionSchema | null = null;
  @Input() conflicts: PermissionConflict[] = [];

  @Output() permissionsChange = new EventEmitter<MenuPermission[]>();
  @Output() autoFix = new EventEmitter<void>();
  @Output() copyFromRole = new EventEmitter<void>();

  presets = PRESETS;
  search = '';
  tree: MenuPermission[] = [];
  private expanded = new Set<number>();
  private extendedOpen = new Set<number>();
  private matchingIds = new Set<number>();

  get coreFlags(): FlagKey[] {
    return (this.schema?.core as FlagKey[]) || ['canAdd', 'canRead', 'canEdit', 'canDelete'];
  }

  ngOnChanges(c: SimpleChanges): void {
    if (c['flatPermissions']) {
      this.tree = this.buildTree(this.flatPermissions);
      // Auto-expand top-level on first load
      if (this.expanded.size === 0) {
        this.tree.forEach(n => this.expanded.add(n.menuId));
      }
      this.recomputeSearch();
    }
  }

  private buildTree(flat: MenuPermission[], parentId: number | null = null): MenuPermission[] {
    return flat
      .filter(m => m.parentMenuId === parentId)
      .sort((a, b) => a.menuOrder - b.menuOrder)
      .map(m => ({ ...m, children: this.buildTree(flat, m.menuId) }));
  }

  // ---- labels / schema helpers ----
  labelFor(flag: string): string { return this.schema?.labels?.[flag] || flag; }
  descFor(flag: string): string { return this.schema?.descriptions?.[flag] || ''; }
  extendedFor(menuName: string): FlagKey[] {
    return (this.schema?.extended?.[menuName] as FlagKey[]) || [];
  }
  extendedCount(node: MenuPermission): number {
    return this.extendedFor(node.menuName).filter(f => !!(node as any)[f]).length;
  }

  // ---- expand / collapse ----
  toggleExpand(id: number): void {
    this.expanded.has(id) ? this.expanded.delete(id) : this.expanded.add(id);
  }
  isExpanded(id: number): boolean { return this.expanded.has(id); }
  toggleExtended(id: number): void {
    this.extendedOpen.has(id) ? this.extendedOpen.delete(id) : this.extendedOpen.add(id);
  }
  isExtendedOpen(id: number): boolean { return this.extendedOpen.has(id); }

  // ---- flag toggle ----
  toggle(node: MenuPermission, flag: FlagKey, value: boolean): void {
    const row = this.flatPermissions.find(p => p.menuId === node.menuId);
    if (!row) return;
    (row as any)[flag] = value;
    // Keep tree node in sync for the checkbox binding
    (node as any)[flag] = value;
    this.emitChange();
  }

  // ---- bulk column ----
  setColumnAll(flag: FlagKey, value: boolean): void {
    const visibleIds = this.visibleMenuIds();
    for (const row of this.flatPermissions) {
      if (visibleIds.has(row.menuId)) {
        (row as any)[flag] = value;
      }
    }
    this.tree = this.buildTree(this.flatPermissions);
    this.emitChange();
  }

  isColumnAllChecked(flag: FlagKey): boolean {
    const visibleIds = this.visibleMenuIds();
    const visible = this.flatPermissions.filter(p => visibleIds.has(p.menuId));
    return visible.length > 0 && visible.every(p => !!(p as any)[flag]);
  }
  isColumnPartialChecked(flag: FlagKey): boolean {
    const visibleIds = this.visibleMenuIds();
    const visible = this.flatPermissions.filter(p => visibleIds.has(p.menuId));
    const count = visible.filter(p => !!(p as any)[flag]).length;
    return count > 0 && count < visible.length;
  }

  // ---- preset ----
  applyPreset(presetId: string): void {
    const preset = this.presets.find(p => p.id === presetId);
    if (!preset) return;
    const flagSet = new Set(preset.flags);
    for (const row of this.flatPermissions) {
      for (const f of ALL_PERMISSION_FLAGS) {
        // Only apply extended flags where the menu supports them —
        // otherwise "canApprove" on a Masters menu becomes no-op noise.
        if (!this.isApplicableFor(row.menuName, f as FlagKey)) continue;
        (row as any)[f] = flagSet.has(f as FlagKey);
      }
    }
    this.tree = this.buildTree(this.flatPermissions);
    this.emitChange();
  }

  private isApplicableFor(menuName: string, flag: FlagKey): boolean {
    // Core flags always apply.
    if (this.coreFlags.includes(flag)) return true;
    return this.extendedFor(menuName).includes(flag);
  }

  // ---- search ----
  onSearch(): void { this.recomputeSearch(); }
  clearSearch(): void { this.search = ''; this.recomputeSearch(); }

  private recomputeSearch(): void {
    this.matchingIds.clear();
    const term = this.search.trim().toLowerCase();
    if (!term) return;
    // Match a node if its name contains the term. Also mark all ancestors
    // as matching so the tree path stays visible.
    const ancestorMap = new Map<number, number | null>();
    for (const p of this.flatPermissions) ancestorMap.set(p.menuId, p.parentMenuId);
    for (const p of this.flatPermissions) {
      if (p.menuName.toLowerCase().includes(term)) {
        let id: number | null = p.menuId;
        while (id !== null) {
          this.matchingIds.add(id);
          id = ancestorMap.get(id) ?? null;
        }
      }
    }
  }

  matchesSearch(node: MenuPermission): boolean {
    if (!this.search.trim()) return true;
    return this.matchingIds.has(node.menuId);
  }

  private visibleMenuIds(): Set<number> {
    if (!this.search.trim()) return new Set(this.flatPermissions.map(p => p.menuId));
    return new Set(this.matchingIds);
  }

  // ---- conflicts ----
  hasConflict(menuId: number): boolean {
    return this.conflicts.some(c => c.menuId === menuId);
  }

  private emitChange(): void {
    this.permissionsChange.emit([...this.flatPermissions]);
  }
}
