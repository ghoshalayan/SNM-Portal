import { Injectable } from '@angular/core';

const ACCESS_TOKEN_KEY = 'snm_access_token';
const REFRESH_TOKEN_KEY = 'snm_refresh_token';
const USER_DATA_KEY = 'snm_user_data';

@Injectable({ providedIn: 'root' })
export class TokenService {
  getAccessToken(): string | null {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  }

  getRefreshToken(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  }

  setTokens(accessToken: string, refreshToken: string): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }

  setUserData(data: any): void {
    localStorage.setItem(USER_DATA_KEY, JSON.stringify(data));
  }

  getUserData(): any {
    const data = localStorage.getItem(USER_DATA_KEY);
    return data ? JSON.parse(data) : null;
  }

  clearTokens(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_DATA_KEY);
  }

  isAuthenticated(): boolean {
    return !!this.getAccessToken();
  }
}
