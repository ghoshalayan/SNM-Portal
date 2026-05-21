import { ErrorHandler, Injectable, NgZone, inject } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { NotificationService } from '../services/notification.service';

/**
 * Global error boundary for the Angular app (Phase 0).
 *
 * Replaces the default Angular ErrorHandler which only logs to console.
 * Behaviour:
 *   * Unhandled component / service exceptions surface as a snackbar
 *     so the user knows something went wrong instead of the UI silently
 *     freezing.
 *   * The raw error + the backend's ``requestId`` (when the error is
 *     an HttpErrorResponse from our error boundary) go to ``console.error``
 *     for in-browser debugging. A future telemetry endpoint hook is
 *     teed off the same method.
 *   * HTTP errors that the AuthInterceptor already handles (401 →
 *     refresh / logout) are *not* re-snackbarred — they reach this
 *     handler only if the interceptor's refresh path itself fails.
 *
 * Wired in app.config.ts via:
 *     { provide: ErrorHandler, useClass: GlobalErrorHandler }
 *
 * Snackbar calls run through NgZone.run() because errors can be thrown
 * from contexts outside the Angular zone (e.g. async pipe in a
 * standalone observable, RxJS subscribe with no zone wrapper) — without
 * the explicit run() the snackbar's CD doesn't tick and the message
 * never appears.
 */
@Injectable()
export class GlobalErrorHandler implements ErrorHandler {
  private readonly notify = inject(NotificationService);
  private readonly zone = inject(NgZone);

  handleError(error: unknown): void {
    const friendly = this.extractFriendlyMessage(error);
    const requestId = this.extractRequestId(error);

    // Always log the raw thing for browser-side debugging.
    // The structured fields here (errorClass / requestId) will be the
    // shape the future telemetry hook ships.
    console.error('[GlobalErrorHandler]', {
      errorClass: (error as any)?.constructor?.name ?? typeof error,
      requestId,
      error,
    });

    // Don't pop a snackbar for known-noise:
    //  * 401: auth interceptor handles refresh/logout already.
    //  * Errors silently filtered upstream (we encode this by setting a
    //    ``_suppressGlobalHandler`` flag on the error object).
    if (this.shouldSuppress(error)) {
      return;
    }

    this.zone.run(() => {
      this.notify.error(
        requestId
          ? `${friendly} (ref: ${requestId})`
          : friendly,
      );
    });
  }

  private extractFriendlyMessage(error: unknown): string {
    if (error instanceof HttpErrorResponse) {
      // The backend error-boundary now returns
      // { code, message, requestId }. Prefer message when present.
      const body = (error.error || {}) as { message?: string; detail?: string };
      if (typeof body === 'string') return body;
      if (body.message) return body.message;
      if (body.detail) return body.detail;
      return `${error.status} ${error.statusText || 'Error'}`;
    }
    if (error instanceof Error && error.message) {
      return error.message;
    }
    if (typeof error === 'string') return error;
    return 'An unexpected error occurred. Please try again.';
  }

  private extractRequestId(error: unknown): string | null {
    if (error instanceof HttpErrorResponse) {
      // Backend sets ``X-Request-Id`` on every response, success or
      // failure. HttpErrorResponse exposes response headers via
      // ``error.headers``.
      const fromHeader = error.headers?.get?.('X-Request-Id');
      if (fromHeader) return fromHeader;
      const body = (error.error || {}) as { requestId?: string };
      if (body && body.requestId) return body.requestId;
    }
    return null;
  }

  private shouldSuppress(error: unknown): boolean {
    if (error instanceof HttpErrorResponse && error.status === 401) {
      // AuthInterceptor handles 401 with refresh + retry; if we're
      // here, the refresh failed and logout is already in progress.
      // No snackbar needed — the user is being redirected to /login.
      return true;
    }
    if (typeof error === 'object' && error !== null
        && (error as any)._suppressGlobalHandler === true) {
      return true;
    }
    return false;
  }
}
