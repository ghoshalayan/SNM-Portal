import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatRadioModule } from '@angular/material/radio';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RoleSettings } from './role-permission.types';

/**
 * Tab 1: role-level flags, grouped into 5 collapsible sections.
 *
 * Dependent flags (peerSubtree ← peerAccess, enforceChildLocationSubset ←
 * locationScopeRequired) are visually nested under their parent and
 * disabled when the parent is off — no silent misconfig.
 */
@Component({
  selector: 'app-role-settings-panel',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    MatCardModule, MatCheckboxModule, MatFormFieldModule, MatIconModule,
    MatInputModule, MatRadioModule, MatTooltipModule,
  ],
  template: `
    <div class="rsp">
      <section class="rsp-section">
        <h3 class="rsp-head">Identity</h3>
        <div class="rsp-row">
          <mat-form-field appearance="outline" class="rsp-field-wide">
            <mat-label>Role name</mat-label>
            <input matInput [value]="settings.roleName" readonly />
            <mat-icon matSuffix matTooltip="Change the role name from the Roles list.">lock</mat-icon>
          </mat-form-field>
          <mat-form-field appearance="outline" class="rsp-field-narrow">
            <mat-label>Hierarchy level</mat-label>
            <input matInput type="number" min="0"
              [(ngModel)]="settings.roleLevel"
              (ngModelChange)="emit()" />
            <mat-icon matSuffix matTooltip="Higher number = more authority. SuperAdmin should be the highest (e.g. 100).">help_outline</mat-icon>
          </mat-form-field>
        </div>
      </section>

      <section class="rsp-section">
        <h3 class="rsp-head">Number Generation &amp; Ownership</h3>
        <p class="rsp-hint">Controls whose code appears in the auto-generated number AND who becomes the record owner.</p>
        <mat-radio-group class="rsp-radios"
          [(ngModel)]="settings.numGenMode"
          (ngModelChange)="emit()">
          <mat-radio-button value="own_code">
            <strong>Use own code</strong>
            <span class="rsp-sub">Owner = self. Simplest path.</span>
          </mat-radio-button>
          <mat-radio-button value="parent_code">
            <strong>Use parent code</strong>
            <span class="rsp-sub">Owner = reporting manager.</span>
          </mat-radio-button>
          <mat-radio-button value="select_code">
            <strong>Select user code</strong>
            <span class="rsp-sub">User picks from a dropdown; requires <em>Gen Under Others</em> per menu.</span>
          </mat-radio-button>
        </mat-radio-group>
      </section>

      <section class="rsp-section">
        <h3 class="rsp-head">Visibility</h3>
        <div class="rsp-row">
          <mat-form-field appearance="outline" class="rsp-field-narrow">
            <mat-label>Downward levels</mat-label>
            <input matInput type="number" min="-1"
              [(ngModel)]="settings.downwardLevels"
              (ngModelChange)="emit()" />
            <mat-icon matSuffix matTooltip="How many levels of subordinates this role sees. -1 = unlimited.">help_outline</mat-icon>
          </mat-form-field>
          <mat-form-field appearance="outline" class="rsp-field-narrow">
            <mat-label>Upward levels</mat-label>
            <input matInput type="number" min="-1"
              [(ngModel)]="settings.upwardLevels"
              (ngModelChange)="emit()" />
            <mat-icon matSuffix matTooltip="How many levels of ancestors this role sees. 0 = none.">help_outline</mat-icon>
          </mat-form-field>
        </div>
        <mat-checkbox color="primary"
          [(ngModel)]="settings.includeSubtreeOnUpward"
          (ngModelChange)="emit()">
          Include subtree on upward
          <span class="rsp-sub">When seeing ancestors, also include their full subtree.</span>
        </mat-checkbox>
        <mat-checkbox color="primary"
          [(ngModel)]="settings.peerAccess"
          (ngModelChange)="onPeerAccessChange()">
          Peer access
          <span class="rsp-sub">View records of users reporting to the same manager.</span>
        </mat-checkbox>
        <div class="rsp-nested">
          <mat-checkbox color="primary"
            [disabled]="!settings.peerAccess"
            [(ngModel)]="settings.peerSubtree"
            (ngModelChange)="emit()">
            Include peers' subtree
            <span class="rsp-sub">Requires Peer access. Also pulls peers' subordinates.</span>
          </mat-checkbox>
        </div>
      </section>

      <section class="rsp-section">
        <h3 class="rsp-head">Location &amp; Transfers</h3>
        <mat-checkbox color="primary"
          [(ngModel)]="settings.locationScopeRequired"
          (ngModelChange)="onLocationScopeChange()">
          Location scope required
          <span class="rsp-sub">Restrict records by the user's assigned location list.</span>
        </mat-checkbox>
        <div class="rsp-nested">
          <mat-checkbox color="primary"
            [disabled]="!settings.locationScopeRequired"
            [(ngModel)]="settings.enforceChildLocationSubset"
            (ngModelChange)="emit()">
            KRO-style subset
            <span class="rsp-sub">User's locations must be a subset of their reporting manager's.</span>
          </mat-checkbox>
        </div>
        <mat-checkbox color="primary"
          [(ngModel)]="settings.canApproveTransfers"
          (ngModelChange)="emit()">
          Can approve transfers
          <span class="rsp-sub">Approve or reject ownership-transfer requests.</span>
        </mat-checkbox>
      </section>

      <section class="rsp-section danger">
        <h3 class="rsp-head">Admin Overrides</h3>
        <mat-checkbox color="warn"
          [(ngModel)]="settings.isCompanyAdmin"
          (ngModelChange)="emit()">
          <strong>Company Admin</strong>
          <span class="rsp-sub danger-text">
            <mat-icon class="rsp-warn-icon">warning</mat-icon>
            Bypasses hierarchy + location filters for the whole company. Use sparingly.
          </span>
        </mat-checkbox>
      </section>
    </div>
  `,
  styles: [`
    .rsp { padding: 8px 4px; }
    .rsp-section {
      padding: 16px 0;
      border-bottom: 1px solid var(--snm-border-divider);
    }
    .rsp-section:last-child { border-bottom: none; }
    .rsp-section.danger {
      background: rgba(198, 40, 40, 0.04);
      border-radius: 8px;
      padding: 12px 16px;
      margin-top: 12px;
      border: 1px solid rgba(198, 40, 40, 0.2);
    }
    .rsp-head {
      margin: 0 0 10px;
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.3px;
      color: var(--snm-accent-dark);
    }
    .rsp-hint {
      margin: 0 0 10px;
      font-size: 12px;
      color: var(--snm-text-muted);
    }
    .rsp-row {
      display: flex; gap: 16px; flex-wrap: wrap;
    }
    .rsp-field-wide { flex: 2 1 320px; }
    .rsp-field-narrow { flex: 0 0 180px; }
    .rsp-radios {
      display: flex; flex-direction: column; gap: 8px;
    }
    .rsp-radios mat-radio-button { display: block; }
    .rsp-sub {
      display: block;
      font-size: 11px;
      color: var(--snm-text-muted);
      font-weight: 400;
      margin-top: 2px;
    }
    mat-checkbox { display: block; margin-bottom: 4px; }
    .rsp-nested {
      margin-left: 28px;
      padding-left: 12px;
      border-left: 2px solid var(--snm-border-divider);
    }
    .danger-text { color: var(--snm-error); }
    .rsp-warn-icon {
      font-size: 14px; width: 14px; height: 14px;
      vertical-align: middle; margin-right: 2px;
      color: var(--snm-error);
    }
  `],
})
export class RoleSettingsPanelComponent {
  @Input({ required: true }) settings!: RoleSettings;
  @Output() settingsChange = new EventEmitter<RoleSettings>();

  emit(): void {
    this.settingsChange.emit({ ...this.settings });
  }

  onPeerAccessChange(): void {
    // When peerAccess turns off, peerSubtree must also turn off —
    // otherwise the disabled checkbox stays "true" and confuses the user.
    if (!this.settings.peerAccess) {
      this.settings.peerSubtree = false;
    }
    this.emit();
  }

  onLocationScopeChange(): void {
    if (!this.settings.locationScopeRequired) {
      this.settings.enforceChildLocationSubset = false;
    }
    this.emit();
  }
}
