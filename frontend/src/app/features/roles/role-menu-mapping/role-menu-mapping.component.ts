import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatRadioModule } from '@angular/material/radio';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { SkeletonLoaderComponent } from '../../../shared/components/skeleton-loader/skeleton-loader.component';

interface MenuPermission {
  menuId: number;
  menuName: string;
  parentMenuId: number | null;
  menuOrder: number;
  canAdd: boolean;
  canRead: boolean;
  canEdit: boolean;
  canDelete: boolean;
  canEditNumber: boolean;
  canApprove?: boolean;
  canRevise?: boolean;
  canTransferOwnership?: boolean;
  canGenerateUnderOthers?: boolean;
  children?: MenuPermission[];
}

/** Menus that support extended permissions (Approve/Revise/Transfer/GenerateUnderOthers).
 * For all other menus, the extended columns are hidden in the UI.
 * Kept dynamic — add to this list to enable extended perms on new modules.
 */
export const EXTENDED_PERM_MENUS = new Set<string>([
  'Quotations', 'Enquiries',
]);

/** Which extended perms each menu supports (kept dynamic per-menu). */
export const MENU_EXTRA_PERMS: Record<string, string[]> = {
  'Quotations': ['canApprove', 'canRevise', 'canTransferOwnership', 'canGenerateUnderOthers'],
  'Enquiries': ['canApprove', 'canTransferOwnership', 'canGenerateUnderOthers'],
};

@Component({
  selector: 'app-role-menu-mapping',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    MatCheckboxModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatRadioModule,
    MatDividerModule,
    SkeletonLoaderComponent,
    MatFormFieldModule,
    MatInputModule,
    MatTooltipModule,
  ],
  templateUrl: './role-menu-mapping.component.html',
  styleUrl: './role-menu-mapping.component.scss',
})
export class RoleMenuMappingComponent implements OnInit {
  roleId!: number;
  flatPermissions: MenuPermission[] = [];
  menuTree: MenuPermission[] = [];
  loading = true;
  saving = false;
  expandedIds = new Set<number>();
  roleName = '';
  numGenMode: string = 'own_code';
  peerAccess = false;
  peerSubtree = false;
  roleLevel = 0;
  locationScopeRequired = true;
  canApproveTransfers = false;
  // RBAC v2 flags
  isCompanyAdmin = false;
  downwardLevels = -1;
  upwardLevels = 0;
  includeSubtreeOnUpward = true;
  enforceChildLocationSubset = false;
  // Legacy (kept for backward compat)
  upwardVisibilityLevels = 0;
  numGenSaving = false;

  constructor(
    private route: ActivatedRoute,
    public router: Router,
    private api: ApiService,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    this.roleId = +this.route.snapshot.params['roleId'];
    if (!this.roleId) {
      this.notify.error('Invalid role');
      this.router.navigate(['/roles']);
      return;
    }
    this.loadRole();
    this.loadPermissions();
    this.loadNumGenMode();
  }

  loadRole(): void {
    this.api.get<any>(`/roles/${this.roleId}`).subscribe({
      next: (role) => (this.roleName = role.roleName),
    });
  }

  loadNumGenMode(): void {
    this.api.get<any>(`/roles/${this.roleId}/num-gen-mode`).subscribe({
      next: (data) => {
        this.numGenMode = data.numGenMode;
        this.peerAccess = data.peerAccess ?? false;
        this.peerSubtree = data.peerSubtree ?? false;
        this.roleLevel = data.roleLevel ?? 0;
        this.locationScopeRequired = data.locationScopeRequired ?? true;
        this.canApproveTransfers = data.canApproveTransfers ?? false;
        this.upwardVisibilityLevels = data.upwardVisibilityLevels ?? 0;
        this.isCompanyAdmin = data.IsCompanyAdmin ?? data.isCompanyAdmin ?? false;
        this.downwardLevels = data.downwardLevels ?? -1;
        this.upwardLevels = data.upwardLevels ?? this.upwardVisibilityLevels;
        this.includeSubtreeOnUpward = data.includeSubtreeOnUpward ?? true;
        this.enforceChildLocationSubset = data.enforceChildLocationSubset ?? false;
      },
    });
  }

  saveRoleSettings(): void {
    this.numGenSaving = true;
    this.api.put(`/roles/${this.roleId}/num-gen-mode`, {
      numGenMode: this.numGenMode,
      peerAccess: this.peerAccess,
      peerSubtree: this.peerSubtree,
      roleLevel: this.roleLevel,
      locationScopeRequired: this.locationScopeRequired,
      canApproveTransfers: this.canApproveTransfers,
      upwardVisibilityLevels: this.upwardVisibilityLevels,
      IsCompanyAdmin: this.isCompanyAdmin,
      downwardLevels: this.downwardLevels,
      upwardLevels: this.upwardLevels,
      includeSubtreeOnUpward: this.includeSubtreeOnUpward,
      enforceChildLocationSubset: this.enforceChildLocationSubset,
    }).subscribe({
      next: () => { this.notify.success('Role settings saved'); this.numGenSaving = false; },
      error: () => { this.notify.error('Failed to save'); this.numGenSaving = false; },
    });
  }

  loadPermissions(): void {
    this.loading = true;
    const start = Date.now();
    this.api.get<MenuPermission[]>(`/menus/role-menu-map/${this.roleId}`).subscribe({
      next: (data) => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => {
          this.flatPermissions = data;
          this.menuTree = this.buildTree(data);
          this.menuTree.forEach(n => this.expandedIds.add(n.menuId));
          this.loading = false;
        }, remaining);
      },
      error: () => {
        const remaining = Math.max(0, 500 - (Date.now() - start));
        setTimeout(() => {
          this.notify.error('Failed to load permissions');
          this.loading = false;
        }, remaining);
      },
    });
  }

  private buildTree(flat: MenuPermission[], parentId: number | null = null): MenuPermission[] {
    return flat
      .filter(m => m.parentMenuId === parentId)
      .sort((a, b) => a.menuOrder - b.menuOrder)
      .map(m => ({
        ...m,
        children: this.buildTree(flat, m.menuId),
      }));
  }

  toggle(menuId: number): void {
    if (this.expandedIds.has(menuId)) {
      this.expandedIds.delete(menuId);
    } else {
      this.expandedIds.add(menuId);
    }
  }

  isExpanded(menuId: number): boolean {
    return this.expandedIds.has(menuId);
  }

  /** Returns the list of extended permission keys this menu supports. */
  extraPerms(menuName: string): string[] {
    return MENU_EXTRA_PERMS[menuName] || [];
  }

  /** Human-readable label for an extended perm column. */
  extraPermLabel(key: string): string {
    const labels: Record<string, string> = {
      canApprove: 'Approve',
      canRevise: 'Revise',
      canTransferOwnership: 'Transfer',
      canGenerateUnderOthers: 'Gen Under Others',
    };
    return labels[key] || key;
  }

  togglePermission(node: MenuPermission, field: 'canAdd' | 'canRead' | 'canEdit' | 'canDelete' | 'canEditNumber' | 'canApprove' | 'canRevise' | 'canTransferOwnership' | 'canGenerateUnderOthers'): void {
    const perm = this.flatPermissions.find(p => p.menuId === node.menuId);
    if (perm) {
      (perm as any)[field] = !(perm as any)[field];
      (node as any)[field] = (perm as any)[field];
    }
  }

  toggleAll(node: MenuPermission, field: 'canAdd' | 'canRead' | 'canEdit' | 'canDelete' | 'canEditNumber' | 'canApprove' | 'canRevise' | 'canTransferOwnership' | 'canGenerateUnderOthers'): void {
    this.togglePermission(node, field);
    const newValue = !!(node as any)[field];
    // Apply to all children recursively
    if (node.children) {
      this.applyToChildren(node.children, field, newValue);
    }
  }

  private applyToChildren(children: MenuPermission[], field: string, value: boolean): void {
    for (const child of children) {
      const perm = this.flatPermissions.find(p => p.menuId === child.menuId);
      if (perm) {
        (perm as any)[field] = value;
        (child as any)[field] = value;
      }
      if (child.children) {
        this.applyToChildren(child.children, field, value);
      }
    }
  }

  save(): void {
    this.saving = true;
    // The backend's Pydantic ``RoleMenuPermission`` defaults every field
    // to false, so any flag NOT in this payload is silently RESET on
    // save. This page's UI doesn't render checkboxes for the newer flags
    // (canApproveAnnexure + the Phase-1 lifecycle flags), but the GET
    // returns them — so we echo whatever was loaded back unchanged.
    // Without this round-trip, saving from the legacy page would clobber
    // flags that an admin had set via the v2 page.
    const payload = this.flatPermissions.map(p => ({
      menuId: p.menuId,
      canAdd: p.canAdd,
      canRead: p.canRead,
      canEdit: p.canEdit,
      canDelete: p.canDelete,
      canEditNumber: p.canEditNumber || false,
      canApprove: (p as any).canApprove || false,
      canRevise: (p as any).canRevise || false,
      canTransferOwnership: (p as any).canTransferOwnership || false,
      canGenerateUnderOthers: (p as any).canGenerateUnderOthers || false,
      canApproveAnnexure: (p as any).canApproveAnnexure || false,
      canConvert: (p as any).canConvert || false,
      canReactivate: (p as any).canReactivate || false,
      canSubmitPO: (p as any).canSubmitPO || false,
      canRejectPO: (p as any).canRejectPO || false,
      canApproveViability: (p as any).canApproveViability || false,
      canUnlockEditQuotation: (p as any).canUnlockEditQuotation || false,
      canUnlockEditPO: (p as any).canUnlockEditPO || false,
      canUnlockEditViability: (p as any).canUnlockEditViability || false,
      canUnlockEditAnnexure: (p as any).canUnlockEditAnnexure || false,
    }));

    this.api.post(`/menus/role-menu-map/${this.roleId}`, payload).subscribe({
      next: () => { this.notify.success('Permissions saved'); this.saving = false; },
      error: () => { this.notify.error('Failed to save permissions'); this.saving = false; },
    });
  }
}
