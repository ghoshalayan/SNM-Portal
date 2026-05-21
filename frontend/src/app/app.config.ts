import { ApplicationConfig, ErrorHandler, provideBrowserGlobalErrorListeners, provideZoneChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptorsFromDi } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { DateAdapter, MAT_DATE_FORMATS, MAT_DATE_LOCALE } from '@angular/material/core';

import { routes } from './app.routes';
import { authInterceptorProvider } from './core/auth/auth.interceptor';
import { SNM_DATE_FORMATS, SnmDateAdapter } from './core/date/snm-date-adapter';
import { GlobalErrorHandler } from './core/error/global-error-handler';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(withInterceptorsFromDi()),
    provideAnimationsAsync(),
    // Replaced provideNativeDateAdapter() with our SnmDateAdapter so all
    // mat-datepicker inputs accept and display dates as dd-MM-yyyy.
    { provide: MAT_DATE_LOCALE, useValue: 'en-IN' },
    { provide: DateAdapter, useClass: SnmDateAdapter },
    { provide: MAT_DATE_FORMATS, useValue: SNM_DATE_FORMATS },
    authInterceptorProvider,
    // Phase 0 global error boundary — unhandled exceptions surface as
    // a snackbar with the backend's request-id; full error logs to
    // console for in-browser debugging.
    { provide: ErrorHandler, useClass: GlobalErrorHandler },
  ],
};
