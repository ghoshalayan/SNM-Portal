import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import {
  DashboardAssignment,
  DashboardAssignmentCreate,
  DashboardCreateRequest,
  DashboardDecorateResponse,
  DashboardDetail,
  DashboardItem,
  DashboardItemCreateRequest,
  DashboardItemUpdateRequest,
  DashboardLayoutRequest,
  DashboardListResponse,
  DashboardScope,
  DashboardUpdateRequest,
} from '../models/schema.types';

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly api = inject(ApiService);

  list(opts?: {
    search?: string;
    includeInactive?: boolean;
    scope?: DashboardScope;
  }): Observable<DashboardListResponse> {
    const params: Record<string, any> = {};
    if (opts?.search) params['search'] = opts.search;
    if (opts?.includeInactive) params['include_inactive'] = true;
    if (opts?.scope) params['scope'] = opts.scope;
    return this.api.get<DashboardListResponse>('/kpi/dashboards', params);
  }

  get(id: number): Observable<DashboardDetail> {
    return this.api.get<DashboardDetail>(`/kpi/dashboards/${id}`);
  }

  create(payload: DashboardCreateRequest): Observable<DashboardDetail> {
    return this.api.post<DashboardDetail>('/kpi/dashboards', payload);
  }

  update(id: number, payload: DashboardUpdateRequest): Observable<DashboardDetail> {
    return this.api.put<DashboardDetail>(`/kpi/dashboards/${id}`, payload);
  }

  delete(id: number): Observable<{ deleted: boolean; dashboard_id: number }> {
    return this.api.delete<{ deleted: boolean; dashboard_id: number }>(`/kpi/dashboards/${id}`);
  }

  addItem(dashboardId: number, payload: DashboardItemCreateRequest): Observable<DashboardItem> {
    return this.api.post<DashboardItem>(`/kpi/dashboards/${dashboardId}/items`, payload);
  }

  updateItem(
    dashboardId: number,
    itemId: number,
    payload: DashboardItemUpdateRequest,
  ): Observable<DashboardItem> {
    return this.api.put<DashboardItem>(`/kpi/dashboards/${dashboardId}/items/${itemId}`, payload);
  }

  removeItem(dashboardId: number, itemId: number): Observable<{ deleted: boolean; item_id: number }> {
    return this.api.delete<{ deleted: boolean; item_id: number }>(
      `/kpi/dashboards/${dashboardId}/items/${itemId}`,
    );
  }

  saveLayout(dashboardId: number, payload: DashboardLayoutRequest): Observable<DashboardDetail> {
    return this.api.put<DashboardDetail>(`/kpi/dashboards/${dashboardId}/layout`, payload);
  }

  autoDecorate(dashboardId: number): Observable<DashboardDecorateResponse> {
    return this.api.post<DashboardDecorateResponse>(
      `/kpi/dashboards/${dashboardId}/auto-decorate`,
      {},
    );
  }

  // ---- Phase A4 — assignments --------------------------------------------

  listAssignments(dashboardId: number): Observable<DashboardAssignment[]> {
    return this.api.get<DashboardAssignment[]>(`/kpi/dashboards/${dashboardId}/assignments`);
  }

  addAssignment(
    dashboardId: number,
    payload: DashboardAssignmentCreate,
  ): Observable<DashboardAssignment> {
    return this.api.post<DashboardAssignment>(
      `/kpi/dashboards/${dashboardId}/assignments`,
      payload,
    );
  }

  revokeAssignment(
    dashboardId: number,
    assignmentId: number,
  ): Observable<{ deleted: boolean; assignment_id: number }> {
    return this.api.delete<{ deleted: boolean; assignment_id: number }>(
      `/kpi/dashboards/${dashboardId}/assignments/${assignmentId}`,
    );
  }
}
