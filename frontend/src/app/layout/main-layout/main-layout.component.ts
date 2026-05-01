import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatMenuModule } from '@angular/material/menu';
import { MatDividerModule } from '@angular/material/divider';
import { MatDialog } from '@angular/material/dialog';
import { Subscription } from 'rxjs';
import { AuthService } from '../../core/auth/auth.service';
import { ThemeService } from '../../core/services/theme.service';
import { CompanyContextService } from '../../core/services/company-context.service';
import { DynamicMenuComponent } from '../../shared/components/dynamic-menu/dynamic-menu.component';
import { CompanySwitcherComponent } from '../../shared/components/company-switcher/company-switcher.component';
import { SkeletonLoaderComponent } from '../../shared/components/skeleton-loader/skeleton-loader.component';
import { ProfileDialogComponent } from '../../shared/components/profile-menu/profile-dialog.component';

@Component({
  selector: 'app-main-layout',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    MatSidenavModule,
    MatToolbarModule,
    MatIconModule,
    MatButtonModule,
    MatTooltipModule,
    MatMenuModule,
    MatDividerModule,
    DynamicMenuComponent,
    CompanySwitcherComponent,
    SkeletonLoaderComponent,
  ],
  templateUrl: './main-layout.component.html',
  styleUrl: './main-layout.component.scss',
})
export class MainLayoutComponent implements OnInit, OnDestroy {
  sidenavOpened = true;
  /** When false, the router-outlet is removed from the DOM, destroying all child components. */
  outletActive = true;
  private companySub?: Subscription;

  constructor(
    public authService: AuthService,
    public themeService: ThemeService,
    private dialog: MatDialog,
    private companyContext: CompanyContextService,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    // On company switch: briefly remove router-outlet so all child components
    // are destroyed and recreated with fresh ngOnInit (new JWT = new company data).
    this.companySub = this.companyContext.companyChanged$.subscribe(() => {
      this.outletActive = false;
      this.cdr.detectChanges();          // Force Angular to remove the outlet NOW

      requestAnimationFrame(() => {
        this.outletActive = true;
        this.cdr.detectChanges();        // Force Angular to re-insert the outlet
      });
    });
  }

  ngOnDestroy(): void {
    this.companySub?.unsubscribe();
  }

  toggleSidenav(): void {
    this.sidenavOpened = !this.sidenavOpened;
  }

  getInitial(name: string): string {
    return (name?.charAt(0) || 'U').toUpperCase();
  }

  openProfile(): void {
    const user = this.authService.getCurrentUser();
    if (!user) return;
    this.dialog.open(ProfileDialogComponent, {
      width: '440px',
      data: {
        userId: user.userId,
        userName: user.userName,
        companyName: user.companyName,
        roleName: user.roleName,
        isSuperAdmin: user.isSuperAdmin,
      },
    });
  }

  logout(): void {
    this.authService.logout();
  }
}
