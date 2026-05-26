import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import {
  CallLogCorrelationResponse,
  CallLogDetail,
  CallLogListParams,
  CallLogListResponse,
} from '../models/schema.types';

/** Read-only client over ``/kpi/settings/call-logs/*`` (shipped 2026-05-25).
 *
 *  Every endpoint requires the ``kpi:settings`` permission (SuperAdmin).
 *  Logging itself is authored on the backend by
 *  ``OpenAICompatibleProvider._post`` via ``call_logger.record``; this
 *  service is just the read projection that powers the Call log tab.
 */
@Injectable({ providedIn: 'root' })
export class CallLogsService {
  private readonly api = inject(ApiService);

  /** Cursor-paginated list. ``next_cursor`` from the previous page is
   *  passed back as ``cursor`` to fetch older rows. */
  list(params: CallLogListParams = {}): Observable<CallLogListResponse> {
    return this.api.get<CallLogListResponse>('/kpi/settings/call-logs', params);
  }

  /** Full detail including request_body / response_body JSON. */
  get(callLogId: number): Observable<CallLogDetail> {
    return this.api.get<CallLogDetail>(`/kpi/settings/call-logs/${callLogId}`);
  }

  /** All calls that share one correlation_id — i.e. the full LLM trace
   *  of a single user-facing operation. Returned chronologically. */
  byCorrelation(correlationId: string): Observable<CallLogCorrelationResponse> {
    return this.api.get<CallLogCorrelationResponse>(
      `/kpi/settings/call-logs/correlation/${encodeURIComponent(correlationId)}`);
  }

  /** Admin "clean slate" — wipes the whole table. Use sparingly. */
  purgeAll(): Observable<void> {
    return this.api.delete<void>('/kpi/settings/call-logs');
  }
}
