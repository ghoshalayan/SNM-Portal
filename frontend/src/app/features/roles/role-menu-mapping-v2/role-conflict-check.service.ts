import { Injectable } from '@angular/core';
import {
  FlagKey,
  MenuPermission,
  PermissionConflict,
} from './role-permission.types';

/**
 * Scans a flat permission list for logical conflicts.
 *
 * All checks follow the same pattern: a modification/delete/approve/revise
 * flag is set but canRead is not — meaning the user could theoretically
 * write but has no way to see the record. Also covers "canAdd without
 * canRead" which is usually still a bug (user can create but can't browse
 * their own records).
 */
@Injectable({ providedIn: 'root' })
export class RoleConflictCheckService {
  check(permissions: MenuPermission[]): PermissionConflict[] {
    const conflicts: PermissionConflict[] = [];
    for (const p of permissions) {
      if (!p.canRead) {
        if (p.canEdit) conflicts.push(this.make(p, 'edit-without-read'));
        if (p.canAdd) conflicts.push(this.make(p, 'add-without-read'));
        if (p.canDelete) conflicts.push(this.make(p, 'delete-without-read'));
        if (p.canApprove) conflicts.push(this.make(p, 'approve-without-read'));
        if (p.canRevise) conflicts.push(this.make(p, 'revise-without-read'));
      }
    }
    return conflicts;
  }

  /** Applies every conflict's `fix` to the matching permission row. */
  autoFix(permissions: MenuPermission[], conflicts: PermissionConflict[]): void {
    const byId = new Map(permissions.map(p => [p.menuId, p] as const));
    for (const c of conflicts) {
      const row = byId.get(c.menuId);
      if (!row) continue;
      for (const f of c.fix) {
        (row as any)[f] = true;
      }
    }
  }

  private make(p: MenuPermission, kind: PermissionConflict['kind']): PermissionConflict {
    const fix: FlagKey[] = ['canRead'];
    const messages: Record<PermissionConflict['kind'], string> = {
      'edit-without-read': `${p.menuName}: can Edit but cannot Read — grant Read or remove Edit.`,
      'add-without-read': `${p.menuName}: can Add but cannot Read — user couldn't browse what they created.`,
      'delete-without-read': `${p.menuName}: can Delete but cannot Read.`,
      'approve-without-read': `${p.menuName}: can Approve but cannot Read — approver can't see the record.`,
      'revise-without-read': `${p.menuName}: can Revise but cannot Read.`,
    };
    return {
      menuId: p.menuId,
      menuName: p.menuName,
      kind,
      message: messages[kind],
      fix,
    };
  }
}
