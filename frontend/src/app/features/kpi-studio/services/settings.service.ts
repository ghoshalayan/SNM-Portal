import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import {
  KpiSettings,
  KpiSettingsUpdate,
  SettingsTestResult,
} from '../models/schema.types';

@Injectable({ providedIn: 'root' })
export class SettingsService {
  private readonly api = inject(ApiService);

  get(): Observable<KpiSettings> {
    return this.api.get<KpiSettings>('/kpi/settings');
  }

  /** Backend never echoes the API key — response only carries
   * ``has_api_key``. Use the same payload shape with the KEEP sentinel
   * for fields the user didn't touch. */
  update(payload: KpiSettingsUpdate): Observable<KpiSettings> {
    return this.api.put<KpiSettings>('/kpi/settings', payload);
  }

  test(): Observable<SettingsTestResult> {
    return this.api.post<SettingsTestResult>('/kpi/settings/test', {});
  }
}
