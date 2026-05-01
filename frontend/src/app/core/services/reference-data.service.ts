import { Injectable } from '@angular/core';
import { Observable, of, shareReplay } from 'rxjs';
import { tap } from 'rxjs/operators';
import { ApiService } from './api.service';

/**
 * Reference data service — caches stable master data that rarely changes.
 *
 * Strategy:
 * - Fetches once per session (first caller), all subsequent callers share the
 *   same Observable via shareReplay. No duplicate requests across components.
 * - Manual invalidation via reset() when admin edits masters.
 *
 * When to use: country lists, state lists, districts, any finite reference
 * dataset that changes rarely (days/weeks cadence).
 *
 * When NOT to use: dynamic data (customers, users, enquiries) — those scale
 * via server-side search. Don't cache growing collections here.
 */
@Injectable({ providedIn: 'root' })
export class ReferenceDataService {
  private caches = new Map<string, Observable<any>>();

  constructor(private api: ApiService) {}

  /**
   * Fetch a reference endpoint with multicast caching.
   * Subsequent calls to the same key return the cached observable immediately.
   */
  fetch<T>(key: string, endpoint: string, params?: any): Observable<T> {
    const cached = this.caches.get(key);
    if (cached) return cached as Observable<T>;

    const stream = this.api.get<T>(endpoint, params).pipe(
      shareReplay({ bufferSize: 1, refCount: false }),
    );
    this.caches.set(key, stream);
    return stream;
  }

  /** Invalidate a single cached key (call after master CRUD). */
  invalidate(key: string): void {
    this.caches.delete(key);
  }

  /** Nuke everything (e.g. on company switch). */
  reset(): void {
    this.caches.clear();
  }

  // --- Convenience helpers for common reference data ---

  getCountries(): Observable<any[]> {
    return this.fetch('countries', '/masters/countries');
  }

  getStates(country?: string): Observable<any[]> {
    const key = country ? `states:${country}` : 'states';
    return this.fetch(key, '/masters/states', country ? { country } : undefined);
  }

  getDistricts(state?: string): Observable<any[]> {
    const key = state ? `districts:${state}` : 'districts';
    return this.fetch(key, '/masters/districts', state ? { state } : undefined);
  }

  getMyLocations(): Observable<any> {
    return this.fetch('my-locations', '/users/my-locations');
  }

  getDeliveryTerms(): Observable<any[]> {
    return this.fetch('delivery-terms', '/masters/delivery-terms');
  }

  getDeliveryModes(): Observable<any[]> {
    return this.fetch('delivery-modes', '/masters/delivery-modes');
  }

  getContactTypes(): Observable<any[]> {
    return this.fetch('contact-types', '/masters/contact-types');
  }
}
