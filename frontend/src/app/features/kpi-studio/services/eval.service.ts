import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from '../../../core/services/api.service';
import {
  EvalCase,
  EvalCaseCreate,
  EvalCaseListResponse,
  EvalCaseUpdate,
  EvalRun,
  EvalRunListResponse,
  EvalRunRequest,
} from '../models/schema.types';

/**
 * Wire to the eval-harness API (T-001). SuperAdmin only at the
 * backend (gated to ``kpi:settings``) — UI hides the menu item for
 * regular users via the standard permission directive.
 */
@Injectable({ providedIn: 'root' })
export class EvalService {
  private readonly api = inject(ApiService);

  // ---- Cases ------------------------------------------------------------

  listCases(includeInactive = false, tag?: string): Observable<EvalCaseListResponse> {
    return this.api.get<EvalCaseListResponse>('/kpi/eval/cases', {
      include_inactive: includeInactive,
      tag: tag || undefined,
    });
  }

  getCase(caseId: number): Observable<EvalCase> {
    return this.api.get<EvalCase>(`/kpi/eval/cases/${caseId}`);
  }

  createCase(payload: EvalCaseCreate): Observable<EvalCase> {
    return this.api.post<EvalCase>('/kpi/eval/cases', payload);
  }

  updateCase(caseId: number, payload: EvalCaseUpdate): Observable<EvalCase> {
    return this.api.put<EvalCase>(`/kpi/eval/cases/${caseId}`, payload);
  }

  deleteCase(caseId: number): Observable<void> {
    return this.api.delete<void>(`/kpi/eval/cases/${caseId}`);
  }

  // ---- Runs -------------------------------------------------------------

  listRuns(limit = 50): Observable<EvalRunListResponse> {
    return this.api.get<EvalRunListResponse>('/kpi/eval/runs', { limit });
  }

  getRun(runId: number): Observable<EvalRun> {
    return this.api.get<EvalRun>(`/kpi/eval/runs/${runId}`);
  }

  triggerRun(payload: EvalRunRequest = {}): Observable<EvalRun> {
    return this.api.post<EvalRun>('/kpi/eval/runs', payload);
  }
}
