import { Injectable } from '@angular/core';
import {
  HttpInterceptor,
  HttpRequest,
  HttpHandler,
  HttpEvent,
  HttpErrorResponse,
  HTTP_INTERCEPTORS,
} from '@angular/common/http';
import { BehaviorSubject, Observable, throwError } from 'rxjs';
import { catchError, filter, switchMap, take } from 'rxjs/operators';
import { TokenService } from './token.service';
import { AuthService } from './auth.service';

/**
 * Endpoints we must NOT auto-refresh on — issuing another refresh when one
 * of these returns 401 is either pointless (refresh itself failing) or
 * causes an infinite loop.
 */
const REFRESH_EXEMPT = [
  '/auth/login',
  '/auth/refresh',
  '/auth/select-company',
  '/auth/switch-company',
];

@Injectable()
export class AuthInterceptor implements HttpInterceptor {
  /** True while a refresh call is in-flight. Subsequent 401s queue on
   *  `refreshedToken$` instead of issuing more /auth/refresh calls.
   */
  private isRefreshing = false;
  /** Emits the new access token when refresh completes (or null on failure). */
  private refreshedToken$ = new BehaviorSubject<string | null>(null);

  constructor(
    private tokenService: TokenService,
    private authService: AuthService,
  ) {}

  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    const authReq = this.attachHeaders(req, this.tokenService.getAccessToken());

    return next.handle(authReq).pipe(
      catchError((error: HttpErrorResponse) => {
        if (error.status !== 401) return throwError(() => error);
        if (this.isRefreshExempt(req)) {
          // 401 from a login/refresh endpoint — hard-logout, no retry.
          this.authService.logout();
          return throwError(() => error);
        }
        return this.handle401(req, next);
      }),
    );
  }

  // ---- helpers ----

  private attachHeaders(req: HttpRequest<any>, token: string | null): HttpRequest<any> {
    const headers: Record<string, string> = {};
    if (token && !req.headers.has('Authorization')) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    // Prevent browser from caching API responses (stale data after CRUD)
    if (req.method === 'GET') {
      headers['Cache-Control'] = 'no-cache, no-store, must-revalidate';
      headers['Pragma'] = 'no-cache';
    }
    return Object.keys(headers).length > 0 ? req.clone({ setHeaders: headers }) : req;
  }

  private isRefreshExempt(req: HttpRequest<any>): boolean {
    return REFRESH_EXEMPT.some(path => req.url.includes(path));
  }

  /**
   * Handle a 401 by calling /auth/refresh, then retrying the original
   * request with the new token. Concurrent 401s share the same refresh
   * call by listening on refreshedToken$.
   */
  private handle401(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    if (this.isRefreshing) {
      // A refresh is already in flight — wait for it, then replay.
      return this.refreshedToken$.pipe(
        filter((t): t is string => t !== null),
        take(1),
        switchMap(token => next.handle(this.attachHeaders(req, token))),
      );
    }

    this.isRefreshing = true;
    this.refreshedToken$.next(null);

    return this.authService.refreshToken().pipe(
      switchMap(response => {
        this.isRefreshing = false;
        this.refreshedToken$.next(response.accessToken);
        return next.handle(this.attachHeaders(req, response.accessToken));
      }),
      catchError(err => {
        // Refresh failed — tokens expired / revoked. Fall back to logout.
        this.isRefreshing = false;
        this.refreshedToken$.next(null);
        this.authService.logout();
        return throwError(() => err);
      }),
    );
  }
}

export const authInterceptorProvider = {
  provide: HTTP_INTERCEPTORS,
  useClass: AuthInterceptor,
  multi: true,
};
