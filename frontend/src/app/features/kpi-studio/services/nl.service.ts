import { Injectable, inject } from '@angular/core';
import { Observable, shareReplay } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import {
  KpiSuggestRequest, KpiSuggestResponse,
  NlGenerateRequest, NlGenerateResponse, NlStatus,
} from '../models/schema.types';

@Injectable({ providedIn: 'root' })
export class NlService {
  private readonly api = inject(ApiService);

  /** Cached after the first call — status doesn't change until the
   * backend restarts, so refetching per editor mount is wasteful. */
  private statusCache$: Observable<NlStatus> | null = null;

  status(): Observable<NlStatus> {
    if (!this.statusCache$) {
      this.statusCache$ = this.api.get<NlStatus>('/kpi/nl/status').pipe(shareReplay(1));
    }
    return this.statusCache$;
  }

  /** Test seam — clears the status cache (useful after admin restarts the backend). */
  resetStatusCache(): void {
    this.statusCache$ = null;
  }

  generate(payload: NlGenerateRequest): Observable<NlGenerateResponse> {
    return this.api.post<NlGenerateResponse>('/kpi/nl/generate', payload);
  }

  /** Phase J — AI proposes a set of KPIs for a given source table.
   * Each item is a fully-validated BuilderSpec plus name +
   * description + compiled SQL preview. */
  suggestKpis(payload: KpiSuggestRequest): Observable<KpiSuggestResponse> {
    return this.api.post<KpiSuggestResponse>('/kpi/nl/suggest-kpis', payload);
  }
}
