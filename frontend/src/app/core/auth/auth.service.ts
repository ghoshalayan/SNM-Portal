import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import { environment } from '../../../environments/environment';
import { TokenService } from './token.service';

export interface CompanyInfo {
  companyId: number;
  companyName: string;
  roleId: number;
  roleName: string;
  isDefault: boolean;
  isSuperAdmin: boolean;
}

export interface LoginResponse {
  tempToken: string;
  userId: number;
  userName: string;
  companies: CompanyInfo[];
}

export interface TokenResponse {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
  userId: number;
  userName: string;
  companyId: number;
  companyName: string;
  roleId: number;
  roleName: string;
  isSuperAdmin: boolean;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private apiUrl = environment.apiUrl + '/auth';
  private currentUserSubject = new BehaviorSubject<TokenResponse | null>(null);
  currentUser$ = this.currentUserSubject.asObservable();

  private tempToken: string | null = null;

  constructor(
    private http: HttpClient,
    private tokenService: TokenService,
    private router: Router,
  ) {
    const userData = this.tokenService.getUserData();
    if (userData) {
      this.currentUserSubject.next(userData);
    }
  }

  login(userLogin: string, password: string): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${this.apiUrl}/login`, {
      userLogin,
      password,
    }).pipe(
      tap(response => {
        this.tempToken = response.tempToken;
      }),
    );
  }

  selectCompany(companyId: number): Observable<TokenResponse> {
    return this.http.post<TokenResponse>(
      `${this.apiUrl}/select-company`,
      { companyId },
      { headers: { Authorization: `Bearer ${this.tempToken}` } },
    ).pipe(
      tap(response => this.handleTokenResponse(response)),
    );
  }

  switchCompany(companyId: number): Observable<TokenResponse> {
    return this.http.post<TokenResponse>(
      `${this.apiUrl}/switch-company`,
      { companyId },
    ).pipe(
      tap(response => this.handleTokenResponse(response)),
    );
  }

  getMyCompanies(): Observable<CompanyInfo[]> {
    return this.http.get<CompanyInfo[]>(`${this.apiUrl}/my-companies`);
  }

  refreshToken(): Observable<TokenResponse> {
    const refreshToken = this.tokenService.getRefreshToken();
    return this.http.post<TokenResponse>(`${this.apiUrl}/refresh`, {
      refreshToken,
    }).pipe(
      tap(response => this.handleTokenResponse(response)),
    );
  }

  logout(): void {
    this.tokenService.clearTokens();
    this.currentUserSubject.next(null);
    this.router.navigate(['/login']);
  }

  isAuthenticated(): boolean {
    return this.tokenService.isAuthenticated();
  }

  getCurrentUser(): TokenResponse | null {
    return this.currentUserSubject.value;
  }

  private handleTokenResponse(response: TokenResponse): void {
    this.tokenService.setTokens(response.accessToken, response.refreshToken);
    this.tokenService.setUserData(response);
    this.currentUserSubject.next(response);
    this.tempToken = null;
  }
}
