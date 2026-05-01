import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import {
  SchemaGraph,
  SchemaListResponse,
  SchemaRefreshResponse,
  TableRelationship,
  TableRelationshipAutoSeedResponse,
  TableRelationshipCreate,
  TableRelationshipListResponse,
} from '../models/schema.types';

@Injectable({ providedIn: 'root' })
export class KpiSchemaService {
  private readonly api = inject(ApiService);

  getTables(): Observable<SchemaListResponse> {
    return this.api.get<SchemaListResponse>('/kpi/schema/tables');
  }

  getGraph(): Observable<SchemaGraph> {
    return this.api.get<SchemaGraph>('/kpi/schema/graph');
  }

  refresh(): Observable<SchemaRefreshResponse> {
    return this.api.post<SchemaRefreshResponse>('/kpi/schema/refresh', {});
  }

  // ---- Phase F — relationships ------------------------------------

  listRelationships(): Observable<TableRelationshipListResponse> {
    return this.api.get<TableRelationshipListResponse>('/kpi/schema/relationships');
  }

  createRelationship(payload: TableRelationshipCreate): Observable<TableRelationship> {
    return this.api.post<TableRelationship>('/kpi/schema/relationships', payload);
  }

  deleteRelationship(id: number): Observable<{ deleted: boolean }> {
    return this.api.delete<{ deleted: boolean }>(`/kpi/schema/relationships/${id}`);
  }

  autoSeedRelationships(): Observable<TableRelationshipAutoSeedResponse> {
    return this.api.post<TableRelationshipAutoSeedResponse>(
      '/kpi/schema/relationships/auto-seed', {},
    );
  }
}
