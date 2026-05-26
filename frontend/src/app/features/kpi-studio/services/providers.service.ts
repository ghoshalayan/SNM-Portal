import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from '../../../core/services/api.service';
import {
  ProviderConfig,
  ProviderConfigCreate,
  ProviderConfigListResponse,
  ProviderConfigUpdate,
  ProviderTestResponse,
} from '../models/schema.types';

/**
 * Multi-provider config wire (2026-05-25 refactor). SuperAdmin-only at
 * the backend (gated to ``kpi:settings``).
 */
@Injectable({ providedIn: 'root' })
export class ProvidersService {
  private readonly api = inject(ApiService);
  private readonly base = '/kpi/settings/providers';

  list(): Observable<ProviderConfigListResponse> {
    return this.api.get<ProviderConfigListResponse>(this.base);
  }

  get(id: number): Observable<ProviderConfig> {
    return this.api.get<ProviderConfig>(`${this.base}/${id}`);
  }

  create(payload: ProviderConfigCreate): Observable<ProviderConfig> {
    return this.api.post<ProviderConfig>(this.base, payload);
  }

  update(id: number, payload: ProviderConfigUpdate): Observable<ProviderConfig> {
    return this.api.put<ProviderConfig>(`${this.base}/${id}`, payload);
  }

  delete(id: number): Observable<void> {
    return this.api.delete<void>(`${this.base}/${id}`);
  }

  /** Per-provider test. ``model`` is optional — when blank the backend
   * uses the provider kind's default. Returns enough detail (model
   * echoed back + response preview) to diagnose mis-routing without
   * leaking the API key. */
  test(id: number, model?: string): Observable<ProviderTestResponse> {
    return this.api.post<ProviderTestResponse>(`${this.base}/${id}/test`, {
      model: model || null,
    });
  }
}
