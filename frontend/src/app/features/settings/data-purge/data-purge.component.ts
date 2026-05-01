import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterModule, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatRadioModule } from '@angular/material/radio';
import { MatSelectModule } from '@angular/material/select';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';

import { ApiService } from '../../../core/services/api.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';

interface CompanyLite {
  companyId: number;
  companyName: string;
}

interface PurgeResponse {
  ok: boolean;
  companyId: number;
  mode: 'soft' | 'hard';
  modules: string[];
  counts: Record<string, number>;
  filesDeleted: number;
  filesFailed: number;
}

/**
 * Must match `PURGE_CONFIRMATION` in backend/app/api/v1/admin.py exactly.
 * The user types this string to enable the Purge button.
 */
const CONFIRM_PHRASE = 'DELETE ALL ENQUIRIES AND QUOTATIONS';

@Component({
  selector: 'app-data-purge',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterModule,
    MatButtonModule, MatCardModule, MatCheckboxModule, MatDividerModule,
    MatFormFieldModule, MatIconModule, MatInputModule, MatProgressSpinnerModule,
    MatRadioModule, MatSelectModule, MatDialogModule,
  ],
  template: `
    <div class="dp-page">
      <mat-card class="dp-card">
        <mat-card-header>
          <mat-card-title>
            <mat-icon class="dp-icon">delete_forever</mat-icon>
            Data Purge
          </mat-card-title>
          <mat-card-subtitle>
            SuperAdmin-only · per-company wipe of enquiries / quotations and their descendants
          </mat-card-subtitle>
        </mat-card-header>

        <mat-card-content>
          <div class="dp-warn">
            <mat-icon>warning</mat-icon>
            <div>
              <strong>This action affects production data.</strong>
              Soft-delete is reversible via direct DB update (set <code>isActive=1</code>);
              hard-delete is permanent and also removes underlying files from storage.
            </div>
          </div>

          <!-- Company picker -->
          <mat-form-field appearance="outline" class="dp-field">
            <mat-label>Target Company</mat-label>
            <mat-select [(ngModel)]="companyId" [disabled]="busy">
              @for (c of companies; track c.companyId) {
                <mat-option [value]="c.companyId">{{ c.companyName }}</mat-option>
              }
            </mat-select>
          </mat-form-field>

          <!-- Module selection -->
          <div class="dp-section">
            <label class="dp-label">Modules to purge</label>
            <div class="dp-checks">
              <mat-checkbox [(ngModel)]="modules.enquiries" [disabled]="busy">
                <strong>Enquiries</strong>
                <span class="dp-hint">incl. details, costing, follow-ups, linked assets</span>
              </mat-checkbox>
              <mat-checkbox [(ngModel)]="modules.quotations" [disabled]="busy">
                <strong>Quotations</strong>
                <span class="dp-hint">
                  incl. details, T&C, follow-ups, viability, annexure, activity log, linked assets
                </span>
              </mat-checkbox>
              <mat-checkbox [(ngModel)]="modules.customers" [disabled]="busy">
                <strong>Customers</strong>
                <span class="dp-hint">
                  incl. contacts, sites · hard-delete requires Enquiries + Quotations to also be purged
                </span>
              </mat-checkbox>
            </div>
          </div>

          <!-- Mode -->
          <div class="dp-section">
            <label class="dp-label">Delete mode</label>
            <mat-radio-group [(ngModel)]="mode" (change)="onModeChange()" [disabled]="busy" class="dp-radios">
              <mat-radio-button value="soft">
                <strong>Soft</strong> — mark rows inactive (recoverable)
              </mat-radio-button>
              <mat-radio-button value="hard">
                <strong>Hard</strong> — permanent DELETE; storage files removed
              </mat-radio-button>
            </mat-radio-group>

            @if (mode === 'hard') {
              <mat-checkbox [(ngModel)]="acknowledgeHard" [disabled]="busy" class="dp-ack">
                I understand this cannot be undone.
              </mat-checkbox>
            }
          </div>

          <!-- Confirmation phrase -->
          <div class="dp-section">
            <label class="dp-label">
              Type <code>{{ confirmPhrase }}</code> to enable the Purge button
            </label>
            <mat-form-field appearance="outline" class="dp-field">
              <input matInput [(ngModel)]="confirmation" [disabled]="busy"
                autocomplete="off" spellcheck="false" />
            </mat-form-field>
          </div>

          <!-- Action row -->
          <div class="dp-actions">
            <button mat-raised-button color="warn"
              [disabled]="!canPurge() || busy"
              (click)="onPurgeClick()">
              @if (busy) {
                <mat-spinner diameter="18" class="dp-inline-spinner"></mat-spinner>
                Purging…
              } @else {
                <ng-container>
                  <mat-icon>delete_forever</mat-icon>
                  Purge Selected Data
                </ng-container>
              }
            </button>
          </div>

          <!-- Last-run summary -->
          @if (lastResult) {
            <mat-divider></mat-divider>
            <div class="dp-result">
              <h3>
                <mat-icon>check_circle</mat-icon>
                Purge complete
                <span class="dp-mode-chip" [class.hard]="lastResult.mode === 'hard'">
                  {{ lastResult.mode }}
                </span>
              </h3>
              <div class="dp-result-body">
                <p>
                  Company #{{ lastResult.companyId }} · modules:
                  <strong>{{ lastResult.modules.join(', ') }}</strong>
                </p>
                @if (lastResult.filesDeleted > 0 || lastResult.filesFailed > 0) {
                  <p>
                    Storage files deleted: <strong>{{ lastResult.filesDeleted }}</strong>
                    @if (lastResult.filesFailed > 0) {
                      · <span class="dp-fail">{{ lastResult.filesFailed }} failed</span>
                    }
                  </p>
                }
                <table class="dp-counts">
                  <thead><tr><th>Table</th><th>Rows affected</th></tr></thead>
                  <tbody>
                    @for (k of countKeys(); track k) {
                      <tr>
                        <td>{{ k }}</td>
                        <td class="num">{{ lastResult.counts[k] | number }}</td>
                      </tr>
                    }
                    @if (countKeys().length === 0) {
                      <tr><td colspan="2" class="dp-muted">Nothing matched — no rows were affected.</td></tr>
                    }
                  </tbody>
                </table>
              </div>
            </div>
          }
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: [`
    /* Full-width card, matches the customer-list layout (padding 24px,
       no max-width cap) for visual consistency across admin pages. */
    .dp-page { padding: 24px; }
    .dp-card mat-card-title {
      display: flex; align-items: center; gap: 8px; font-size: 18px;
    }
    .dp-icon { color: var(--snm-error); }

    .dp-warn {
      display: flex; gap: 12px; padding: 12px 16px;
      background: var(--snm-error-bg);
      border: 1px solid rgba(198, 40, 40, 0.3);
      border-radius: 8px;
      margin: 12px 0 20px;
      font-size: 13px;
      color: var(--snm-text-primary);
    }
    .dp-warn mat-icon { color: var(--snm-error); flex-shrink: 0; }
    .dp-warn code {
      font-family: monospace;
      background: rgba(0,0,0,0.06);
      padding: 1px 4px; border-radius: 3px;
    }

    .dp-section { margin-bottom: 20px; }
    .dp-label {
      display: block;
      font-size: 12px;
      font-weight: 600;
      color: var(--snm-text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.3px;
      margin-bottom: 10px;
    }
    .dp-label code {
      text-transform: none;
      font-family: monospace;
      background: var(--snm-accent-subtle);
      color: var(--snm-accent-dark);
      padding: 2px 8px; border-radius: 4px;
      letter-spacing: 0;
    }
    .dp-field { width: 100%; }
    .dp-checks, .dp-radios {
      display: flex; flex-direction: column; gap: 8px;
    }
    .dp-checks mat-checkbox .dp-hint,
    .dp-radios mat-radio-button {
      display: block;
    }
    .dp-hint {
      display: block;
      font-size: 11px;
      color: var(--snm-text-muted);
      font-weight: 400;
      margin-left: 4px;
    }
    .dp-ack {
      margin-top: 12px;
      padding-left: 8px;
      border-left: 3px solid #c62828;
    }

    .dp-actions {
      display: flex; justify-content: flex-end;
      margin-top: 20px;
    }
    .dp-inline-spinner { display: inline-block; margin-right: 8px; vertical-align: middle; }

    .dp-result { margin-top: 20px; padding-top: 12px; }
    .dp-result h3 {
      display: flex; align-items: center; gap: 8px;
      font-size: 15px; font-weight: 600; margin: 0 0 12px;
      color: var(--snm-text-primary);
    }
    .dp-result h3 mat-icon { color: #4caf50; }
    .dp-mode-chip {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 10px;
      border-radius: 12px;
      background: rgba(91, 143, 217, 0.15);
      color: var(--snm-accent-dark);
      border: 1px solid rgba(91, 143, 217, 0.3);
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .dp-mode-chip.hard {
      background: rgba(198, 40, 40, 0.15);
      color: var(--snm-error);
      border-color: rgba(198, 40, 40, 0.3);
    }
    .dp-counts {
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
      font-size: 13px;
    }
    .dp-counts th, .dp-counts td {
      border: 1px solid var(--snm-border-divider);
      padding: 6px 10px;
    }
    .dp-counts th {
      background: var(--snm-bg-header-row);
      font-size: 12px; font-weight: 600;
      text-align: left;
      text-transform: uppercase; letter-spacing: 0.3px;
      color: var(--snm-text-secondary);
    }
    .dp-counts td.num { text-align: right; font-variant-numeric: tabular-nums; }
    .dp-muted { color: var(--snm-text-muted); text-align: center; font-style: italic; }
    .dp-fail { color: var(--snm-error); font-weight: 600; }
  `],
})
export class DataPurgeComponent implements OnInit {
  confirmPhrase = CONFIRM_PHRASE;

  companies: CompanyLite[] = [];
  companyId: number | null = null;

  modules = { enquiries: false, quotations: false, customers: false };
  mode: 'soft' | 'hard' = 'soft';
  acknowledgeHard = false;
  confirmation = '';

  busy = false;
  lastResult: PurgeResponse | null = null;

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    private dialog: MatDialog,
    private router: Router,
  ) {}

  ngOnInit(): void {
    // Route guard already enforces SuperAdmin, but belt-and-braces:
    const userData = JSON.parse(localStorage.getItem('snm_user_data') || '{}');
    if (!userData.isSuperAdmin) {
      this.notify.error('SuperAdmin access required');
      this.router.navigate(['/dashboard']);
      return;
    }
    this.api.get<CompanyLite[]>('/companies').subscribe({
      next: res => {
        this.companies = res || [];
        if (this.companies.length === 1) this.companyId = this.companies[0].companyId;
      },
      error: (e) => this.notify.error(e?.error?.detail || 'Failed to load companies'),
    });
  }

  onModeChange(): void {
    if (this.mode === 'soft') this.acknowledgeHard = false;
  }

  canPurge(): boolean {
    if (!this.companyId) return false;
    if (!this.modules.enquiries && !this.modules.quotations && !this.modules.customers) return false;
    if (this.mode === 'hard' && !this.acknowledgeHard) return false;
    return this.confirmation === CONFIRM_PHRASE;
  }

  onPurgeClick(): void {
    const selected = Object.entries(this.modules).filter(([, v]) => v).map(([k]) => k);
    const co = this.companies.find(c => c.companyId === this.companyId);
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: `Confirm ${this.mode.toUpperCase()} purge`,
        message:
          `You are about to ${this.mode === 'hard' ? 'permanently DELETE' : 'soft-delete'} ` +
          `${selected.join(' and ')} for "${co?.companyName || '#' + this.companyId}". ` +
          (this.mode === 'hard' ? 'Storage files will also be removed. ' : '') +
          'Proceed?',
        confirmText: this.mode === 'hard' ? 'Yes, hard delete' : 'Yes, soft delete',
        confirmColor: 'warn',
      },
      width: '500px',
    });
    ref.afterClosed().subscribe(ok => {
      if (ok) this.runPurge(selected);
    });
  }

  private runPurge(selected: string[]): void {
    this.busy = true;
    this.lastResult = null;
    this.api.post<PurgeResponse>('/admin/data-purge', {
      companyId: this.companyId,
      modules: selected,
      mode: this.mode,
      confirmation: this.confirmation,
      acknowledgeHardDelete: this.mode === 'hard' ? this.acknowledgeHard : false,
    }).subscribe({
      next: res => {
        this.busy = false;
        this.lastResult = res;
        // Force user to re-type the phrase before another run.
        this.confirmation = '';
        this.acknowledgeHard = false;
        const total = Object.values(res.counts).reduce((a, b) => a + b, 0);
        this.notify.success(`Purge complete — ${total} row${total === 1 ? '' : 's'} affected.`);
      },
      error: (e) => {
        this.busy = false;
        this.notify.error(e?.error?.detail || 'Purge failed.');
      },
    });
  }

  countKeys(): string[] {
    return Object.keys(this.lastResult?.counts || {}).sort();
  }
}
