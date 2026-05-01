import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Subscription } from 'rxjs';
import { AuthService, TokenResponse } from '../../../core/auth/auth.service';
import { CompanyContextService } from '../../../core/services/company-context.service';
import { TokenService } from '../../../core/auth/token.service';

@Component({
  selector: 'app-company-switcher',
  standalone: true,
  imports: [CommonModule, MatSelectModule, MatFormFieldModule, MatProgressSpinnerModule],
  template: `
    @if (companies.length > 1) {
      <mat-form-field appearance="outline" class="company-select">
        <mat-select [value]="activeCompanyId" [disabled]="switching" (selectionChange)="onSwitch($event.value)">
          @for (c of companies; track c.companyId) {
            <mat-option [value]="c.companyId">{{ c.companyName }}</mat-option>
          }
        </mat-select>
        @if (switching) {
          <mat-spinner diameter="18" class="switch-spinner"></mat-spinner>
        }
      </mat-form-field>
    } @else if (companies.length === 1) {
      <span class="company-name">{{ companies[0].companyName }}</span>
    }
  `,
  styles: [`
    .company-select {
      width: 200px;
      margin: 0 1rem;
    }
    .company-select ::ng-deep .mat-mdc-form-field-subscript-wrapper { display: none; }
    .company-select ::ng-deep .mdc-notched-outline__leading,
    .company-select ::ng-deep .mdc-notched-outline__notch,
    .company-select ::ng-deep .mdc-notched-outline__trailing {
      border-color: var(--snm-border-field) !important;
    }
    .company-select ::ng-deep .mat-mdc-select-value-text {
      color: var(--snm-text-primary) !important;
    }
    .company-select ::ng-deep .mat-mdc-select-arrow {
      color: var(--snm-text-muted) !important;
    }
    .company-name { margin: 0 1rem; font-size: 14px; font-weight: 500; color: var(--snm-text-secondary); }
    .switch-spinner { position: absolute; right: 32px; top: 50%; transform: translateY(-50%); }
  `],
})
export class CompanySwitcherComponent implements OnInit, OnDestroy {
  companies: { companyId: number; companyName: string }[] = [];
  activeCompanyId: number | null = null;
  switching = false;
  private subs: Subscription[] = [];

  constructor(
    private authService: AuthService,
    private companyContext: CompanyContextService,
    private tokenService: TokenService,
  ) {}

  ngOnInit(): void {
    const userData = this.tokenService.getUserData();
    if (userData) {
      this.activeCompanyId = userData.companyId;
      this.authService.getMyCompanies().subscribe({
        next: (companies) => {
          this.companies = companies;
        },
        error: () => {
          this.companies = [{ companyId: userData.companyId, companyName: userData.companyName }];
        },
      });
    }

    // Keep activeCompanyId in sync after company switch
    this.subs.push(
      this.authService.currentUser$.subscribe(user => {
        if (user) {
          this.activeCompanyId = user.companyId;
        }
      }),
    );

    // Disable dropdown while switch is in progress
    this.subs.push(
      this.companyContext.switching$.subscribe(val => this.switching = val),
    );
  }

  ngOnDestroy(): void {
    this.subs.forEach(s => s.unsubscribe());
  }

  onSwitch(companyId: number): void {
    this.companyContext.switchCompany(companyId);
  }
}
