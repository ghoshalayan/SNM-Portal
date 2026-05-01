import { Injectable } from '@angular/core';
import { BehaviorSubject, Subject, forkJoin, switchMap } from 'rxjs';
import { AuthService } from '../auth/auth.service';
import { MenuService } from './menu.service';

@Injectable({ providedIn: 'root' })
export class CompanyContextService {
  private companyChangedSubject = new Subject<number>();
  companyChanged$ = this.companyChangedSubject.asObservable();

  /** True while a company switch is in progress. */
  private switchingSubject = new BehaviorSubject<boolean>(false);
  switching$ = this.switchingSubject.asObservable();

  constructor(
    private authService: AuthService,
    private menuService: MenuService,
  ) {}

  switchCompany(companyId: number): void {
    this.switchingSubject.next(true);
    this.menuService.clearMenu();

    // switchMap ensures token is stored BEFORE menu/permissions are fetched
    this.authService.switchCompany(companyId).pipe(
      switchMap((response) =>
        forkJoin([
          this.menuService.loadUserMenu(),
          this.menuService.loadPermissions(response.roleId, response.isSuperAdmin),
        ])
      ),
    ).subscribe({
      next: () => {
        this.switchingSubject.next(false);
        this.companyChangedSubject.next(companyId);
      },
      error: () => {
        this.switchingSubject.next(false);
        // Token was already swapped — still notify so outlet refreshes with new company data
        this.companyChangedSubject.next(companyId);
        // Reload menu with whatever token we have so sidebar isn't stuck on skeleton
        this.menuService.loadUserMenu().subscribe();
      },
    });
  }
}
