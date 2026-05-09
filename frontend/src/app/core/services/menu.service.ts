import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, of, tap } from 'rxjs';
import { ApiService } from './api.service';

export interface MenuNode {
  menuId: number;
  menuName: string;
  menuUrl: string | null;
  menuIcon: string | null;
  menuOrder: number;
  children: MenuNode[];
}

export interface MenuPermissionMap {
  [menuName: string]: {
    canAdd: boolean;
    canRead: boolean;
    canEdit: boolean;
    canDelete: boolean;
    canEditNumber: boolean;
    canApprove: boolean;
    canRevise: boolean;
    canTransferOwnership: boolean;
    canGenerateUnderOthers: boolean;
    /** Granted only to the "Commercial HOD" role. Gates annexure
     *  approval and lets the holder edit annexures even after they
     *  are approved (override of the regular post-approval lock). */
    canApproveAnnexure: boolean;
    // ----- Phase 1 lifecycle flags. Only meaningful on Quotations. -----
    canConvert: boolean;
    canReactivate: boolean;
    canSubmitPO: boolean;
    canRejectPO: boolean;
    canApproveViability: boolean;
    canUnlockEditQuotation: boolean;
    canUnlockEditPO: boolean;
    canUnlockEditViability: boolean;
    canUnlockEditAnnexure: boolean;
  };
}

@Injectable({ providedIn: 'root' })
export class MenuService {
  private menuTreeSubject = new BehaviorSubject<MenuNode[]>([]);
  menuTree$ = this.menuTreeSubject.asObservable();

  private permissionsMap: MenuPermissionMap = {};
  private _isSuperAdmin = false;

  constructor(private api: ApiService) {}

  loadUserMenu(): Observable<MenuNode[]> {
    return this.api.get<MenuNode[]>('/menus/user-tree').pipe(
      tap(tree => this.menuTreeSubject.next(tree)),
    );
  }

  loadPermissions(roleId: number, isSuperAdmin: boolean): Observable<any[]> {
    this._isSuperAdmin = isSuperAdmin;

    // SuperAdmins have full access to everything — no need to fetch role-menu-map
    if (isSuperAdmin) {
      this.permissionsMap = {};
      return of([]);
    }

    return this.api.get<any[]>(`/menus/role-menu-map/${roleId}`).pipe(
      tap(perms => {
        this.permissionsMap = {};
        for (const p of perms) {
          this.permissionsMap[p.menuName] = {
            canAdd: p.canAdd,
            canRead: p.canRead,
            canEdit: p.canEdit,
            canDelete: p.canDelete,
            canEditNumber: p.canEditNumber,
            canApprove: p.canApprove || false,
            canRevise: p.canRevise || false,
            canTransferOwnership: p.canTransferOwnership || false,
            canGenerateUnderOthers: p.canGenerateUnderOthers || false,
            canApproveAnnexure: p.canApproveAnnexure || false,
            // Phase 1 lifecycle flags
            canConvert: p.canConvert || false,
            canReactivate: p.canReactivate || false,
            canSubmitPO: p.canSubmitPO || false,
            canRejectPO: p.canRejectPO || false,
            canApproveViability: p.canApproveViability || false,
            canUnlockEditQuotation: p.canUnlockEditQuotation || false,
            canUnlockEditPO: p.canUnlockEditPO || false,
            canUnlockEditViability: p.canUnlockEditViability || false,
            canUnlockEditAnnexure: p.canUnlockEditAnnexure || false,
          };
        }
      }),
    );
  }

  hasPermission(menuName: string, action: string): boolean {
    if (this._isSuperAdmin) return true;
    const perm = this.permissionsMap[menuName];
    if (!perm) return false;
    return (perm as any)[action] || false;
  }

  getPermissionsMap(): MenuPermissionMap {
    return this.permissionsMap;
  }

  clearMenu(): void {
    this.menuTreeSubject.next([]);
    this.permissionsMap = {};
  }
}
