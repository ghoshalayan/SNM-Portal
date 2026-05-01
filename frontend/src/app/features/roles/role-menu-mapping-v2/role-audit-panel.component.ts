import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../../core/services/api.service';
import { AuditRow } from './role-permission.types';

/**
 * Newest-first audit trail for a role's permission changes.
 * Loads lazily on first view (when the user opens the Audit tab).
 */
@Component({
  selector: 'app-role-audit-panel',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    <div class="rap">
      @if (loading) {
        <div class="rap-loading"><mat-spinner diameter="32"></mat-spinner></div>
      } @else if (rows.length === 0) {
        <div class="rap-empty">
          <mat-icon>history_toggle_off</mat-icon>
          <p>No permission changes recorded yet.</p>
          <span class="rap-hint">Audit entries start accumulating after the next save.</span>
        </div>
      } @else {
        <div class="rap-hint">Showing the last {{ rows.length }} change{{ rows.length === 1 ? '' : 's' }}, newest first.</div>
        <table class="rap-table">
          <thead>
            <tr>
              <th>When</th>
              <th>Menu</th>
              <th>Flag</th>
              <th>Change</th>
              <th>By</th>
            </tr>
          </thead>
          <tbody>
            @for (r of rows; track r.auditId) {
              <tr>
                <td>{{ r.changedon | date:'dd-MM-yyyy HH:mm' }}</td>
                <td>{{ r.menuName }}</td>
                <td>{{ r.field }}</td>
                <td>
                  <span class="chip" [class.on]="r.newValue" [class.off]="!r.newValue">
                    {{ r.oldValue === null ? '—' : (r.oldValue ? '✓' : '✗') }} → {{ r.newValue ? '✓' : '✗' }}
                  </span>
                </td>
                <td>{{ r.changedbyName || ('#' + r.changedby) }}</td>
              </tr>
            }
          </tbody>
        </table>
      }
    </div>
  `,
  styles: [`
    .rap { padding: 4px; }
    .rap-loading { display: flex; justify-content: center; padding: 32px; }
    .rap-empty {
      text-align: center; padding: 40px 20px;
      color: var(--snm-text-muted);
    }
    .rap-empty mat-icon { font-size: 40px; width: 40px; height: 40px; opacity: 0.5; }
    .rap-empty p { margin: 12px 0 4px; }
    .rap-hint { font-size: 12px; color: var(--snm-text-muted); margin-bottom: 8px; }
    .rap-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .rap-table th, .rap-table td {
      border-bottom: 1px solid var(--snm-border-divider);
      padding: 6px 10px;
      text-align: left;
    }
    .rap-table th {
      background: var(--snm-bg-header-row);
      font-size: 12px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.3px;
      color: var(--snm-text-secondary);
    }
    .chip {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 10px;
      font-size: 12px;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }
    .chip.on {
      background: rgba(46, 125, 50, 0.12);
      color: #2e7d32;
      border: 1px solid rgba(46, 125, 50, 0.3);
    }
    .chip.off {
      background: rgba(198, 40, 40, 0.12);
      color: #c62828;
      border: 1px solid rgba(198, 40, 40, 0.3);
    }
  `],
})
export class RoleAuditPanelComponent implements OnChanges {
  @Input({ required: true }) roleId!: number;
  /** Set to true by the shell when the audit tab is first opened. Prevents
   *  a redundant fetch for users who never click over to this tab. */
  @Input() active = false;

  loading = false;
  rows: AuditRow[] = [];
  private loaded = false;

  constructor(private api: ApiService) {}

  ngOnChanges(c: SimpleChanges): void {
    if (c['active']?.currentValue && !this.loaded) this.load();
    if (c['roleId']) this.loaded = false;
  }

  private load(): void {
    if (!this.roleId) return;
    this.loading = true;
    this.api.get<AuditRow[]>(`/menus/role-menu-map/${this.roleId}/audit`).subscribe({
      next: (rs) => { this.rows = rs || []; this.loading = false; this.loaded = true; },
      error: () => { this.loading = false; },
    });
  }
}
