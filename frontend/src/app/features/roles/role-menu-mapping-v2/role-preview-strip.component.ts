import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MenuPermission } from './role-permission.types';

/**
 * Plain-English summary of what the role can do. Reads the flat permissions
 * array and renders three bulletpoints: View / Edit / Approve. Non-technical
 * admins get a gut check before saving.
 */
@Component({
  selector: 'app-role-preview-strip',
  standalone: true,
  imports: [CommonModule, MatIconModule],
  template: `
    <div class="preview">
      <div class="preview-head">
        <mat-icon>auto_awesome</mat-icon>
        <span>This role can…</span>
      </div>
      <ul class="preview-lines">
        <li><strong>View:</strong> {{ viewList || 'nothing' }}</li>
        <li><strong>Edit:</strong> {{ editList || '—' }}</li>
        <li><strong>Approve:</strong> {{ approveList || '—' }}</li>
        <li class="negative" *ngIf="negativeList">
          <strong>Cannot:</strong> {{ negativeList }}
        </li>
      </ul>
    </div>
  `,
  styles: [`
    .preview {
      padding: 12px 16px;
      background: var(--snm-accent-subtle);
      border: 1px solid rgba(91, 143, 217, 0.25);
      border-radius: 10px;
      margin: 8px 0 16px;
    }
    .preview-head {
      display: flex; align-items: center; gap: 6px;
      font-size: 12px; font-weight: 700;
      color: var(--snm-accent-dark);
      text-transform: uppercase; letter-spacing: 0.4px;
      margin-bottom: 6px;
    }
    .preview-head mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .preview-lines {
      list-style: none;
      padding: 0; margin: 0;
      font-size: 13px;
      line-height: 1.6;
      color: var(--snm-text-primary);
    }
    .preview-lines li strong {
      color: var(--snm-accent-dark);
      margin-right: 4px;
    }
    .preview-lines li.negative strong { color: var(--snm-error); }
  `],
})
export class RolePreviewStripComponent {
  @Input() permissions: MenuPermission[] = [];

  get viewList(): string {
    return this.listMenus(p => !!p.canRead);
  }
  get editList(): string {
    return this.listMenus(p => !!p.canEdit || !!p.canAdd);
  }
  get approveList(): string {
    return this.listMenus(p => !!p.canApprove);
  }
  /** Menus where the role has Read but no Delete — called out as "cannot delete".
   *  Presented positively via a concise "Cannot: Delete [X, Y]" line when relevant. */
  get negativeList(): string {
    const readable = this.permissions.filter(p => p.canRead);
    const nonDeletable = readable.filter(p => !p.canDelete);
    if (nonDeletable.length === 0 || nonDeletable.length === readable.length) {
      // Either everything deletable or nothing — "cannot" line would be
      // noise ("Delete: nothing" is already implied). Skip.
      return '';
    }
    const names = nonDeletable.map(p => p.menuName);
    return `Delete — ${this.pretty(names)}`;
  }

  private listMenus(predicate: (p: MenuPermission) => boolean): string {
    const names = this.permissions.filter(predicate).map(p => p.menuName);
    return this.pretty(names);
  }

  /** Compact formatting: first ~6 names, then "+N more" to avoid a wall of text. */
  private pretty(names: string[]): string {
    if (names.length === 0) return '';
    if (names.length <= 6) return names.join(' · ');
    const head = names.slice(0, 5).join(' · ');
    return `${head} · +${names.length - 5} more`;
  }
}
