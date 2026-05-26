import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from '../../../core/services/api.service';
import {
  ScheduledJobListResponse,
  ScheduledJobRunListResponse,
  ScheduledJobTriggerResponse,
} from '../models/schema.types';

/**
 * Wire to the scheduler admin API (T-003). SuperAdmin only at the
 * backend (gated to ``kpi:settings``).
 */
@Injectable({ providedIn: 'root' })
export class JobsService {
  private readonly api = inject(ApiService);

  listJobs(): Observable<ScheduledJobListResponse> {
    return this.api.get<ScheduledJobListResponse>('/kpi/jobs');
  }

  listRuns(name: string, limit = 50): Observable<ScheduledJobRunListResponse> {
    return this.api.get<ScheduledJobRunListResponse>(
      `/kpi/jobs/${encodeURIComponent(name)}/runs`,
      { limit },
    );
  }

  triggerJob(name: string): Observable<ScheduledJobTriggerResponse> {
    return this.api.post<ScheduledJobTriggerResponse>(
      `/kpi/jobs/${encodeURIComponent(name)}/trigger`, {},
    );
  }
}
