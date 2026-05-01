import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import {
  ExecutionResult,
  KpiCreateRequest,
  KpiDetail,
  KpiListResponse,
  KpiPreviewRequest,
  KpiRunRequest,
  KpiUpdateRequest,
} from '../models/schema.types';

@Injectable({ providedIn: 'root' })
export class KpiService {
  private readonly api = inject(ApiService);

  list(opts?: { search?: string; includeInactive?: boolean }): Observable<KpiListResponse> {
    const params: Record<string, any> = {};
    if (opts?.search) params['search'] = opts.search;
    if (opts?.includeInactive) params['include_inactive'] = true;
    return this.api.get<KpiListResponse>('/kpi/kpis', params);
  }

  get(id: number): Observable<KpiDetail> {
    return this.api.get<KpiDetail>(`/kpi/kpis/${id}`);
  }

  create(payload: KpiCreateRequest): Observable<KpiDetail> {
    return this.api.post<KpiDetail>('/kpi/kpis', payload);
  }

  update(id: number, payload: KpiUpdateRequest): Observable<KpiDetail> {
    return this.api.put<KpiDetail>(`/kpi/kpis/${id}`, payload);
  }

  delete(id: number): Observable<{ deleted: boolean; kpi_id: number }> {
    return this.api.delete<{ deleted: boolean; kpi_id: number }>(`/kpi/kpis/${id}`);
  }

  preview(payload: KpiPreviewRequest): Observable<ExecutionResult> {
    return this.api.post<ExecutionResult>('/kpi/kpis/preview', payload);
  }

  /** Optional ``period`` body filters by time-window. Empty body still
   * works (the backend defaults to "all time"). */
  run(id: number, body: KpiRunRequest = {}): Observable<ExecutionResult> {
    return this.api.post<ExecutionResult>(`/kpi/kpis/${id}/run`, body);
  }
}
