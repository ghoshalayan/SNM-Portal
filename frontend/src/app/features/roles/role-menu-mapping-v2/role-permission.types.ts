/** Shared types for the v2 role-menu permissions UI. */

/** One permission row — a single menu + its flag state for the role. */
export interface MenuPermission {
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

/** Core + extended flag shape returned by GET /menus/permission-schema. */
export interface PermissionSchema {
  core: string[];
  extended: Record<string, string[]>;
  labels: Record<string, string>;
  descriptions: Record<string, string>;
}

/** Role-level settings (non-menu flags). Bound to the settings panel. */
export interface RoleSettings {
  roleName: string;
  roleLevel: number;
  numGenMode: 'own_code' | 'parent_code' | 'select_code';
  peerAccess: boolean;
  peerSubtree: boolean;
  locationScopeRequired: boolean;
  canApproveTransfers: boolean;
  isCompanyAdmin: boolean;
  downwardLevels: number;
  upwardLevels: number;
  includeSubtreeOnUpward: boolean;
  enforceChildLocationSubset: boolean;
}

export const ALL_PERMISSION_FLAGS: (keyof MenuPermission)[] = [
  'canAdd', 'canRead', 'canEdit', 'canDelete', 'canEditNumber',
  'canApprove', 'canRevise', 'canTransferOwnership', 'canGenerateUnderOthers',
];

export type FlagKey =
  | 'canAdd' | 'canRead' | 'canEdit' | 'canDelete' | 'canEditNumber'
  | 'canApprove' | 'canRevise' | 'canTransferOwnership' | 'canGenerateUnderOthers';

/** Preset templates for quick role baseline. */
export interface PermissionPreset {
  id: string;
  label: string;
  description: string;
  /** Only these flags get `true` on each menu; everything else = false. */
  flags: FlagKey[];
}

export const PRESETS: PermissionPreset[] = [
  {
    id: 'reader',
    label: 'Reader',
    description: 'View everything, cannot change anything.',
    flags: ['canRead'],
  },
  {
    id: 'editor',
    label: 'Editor',
    description: 'View, add, edit. Cannot delete or approve.',
    flags: ['canRead', 'canAdd', 'canEdit'],
  },
  {
    id: 'approver',
    label: 'Approver',
    description: 'View + approve / revise. Cannot add or edit.',
    flags: ['canRead', 'canApprove', 'canRevise'],
  },
  {
    id: 'full',
    label: 'Full access',
    description: 'All flags on every menu. Use sparingly.',
    flags: [
      'canRead', 'canAdd', 'canEdit', 'canDelete', 'canEditNumber',
      'canApprove', 'canRevise', 'canTransferOwnership', 'canGenerateUnderOthers',
    ],
  },
  {
    id: 'clear',
    label: 'Clear all',
    description: 'Reset every flag on every menu to false.',
    flags: [],
  },
];

/** Result of running the conflict checker across current permissions. */
export interface PermissionConflict {
  menuId: number;
  menuName: string;
  kind: 'edit-without-read' | 'add-without-read' | 'delete-without-read'
      | 'approve-without-read' | 'revise-without-read';
  message: string;
  /** Flags that need to be flipped to `true` to resolve. */
  fix: FlagKey[];
}

/** Audit row returned by GET /menus/role-menu-map/{id}/audit. */
export interface AuditRow {
  auditId: number;
  menuId: number;
  menuName: string;
  field: string;
  oldValue: boolean | null;
  newValue: boolean | null;
  changedby?: number;
  changedbyName?: string;
  changedon: string;
}
