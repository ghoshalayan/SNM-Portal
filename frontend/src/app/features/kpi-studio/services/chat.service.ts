import { Injectable, inject } from '@angular/core';
import { Observable, Subscriber } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import { TokenService } from '../../../core/auth/token.service';
import { environment } from '../../../../environments/environment';
import {
  ChatMessage,
  ChatSessionDetail,
  ChatSessionListResponse,
  ChatTurnResponse,
  NlAgentStep,
} from '../models/schema.types';

/**
 * Discriminated union of events the streaming chat endpoint can emit.
 * Mirrors the backend's SSE event shapes — see
 * ``kpi_studio.api.chat.send_turn_stream``.
 */
export type ChatStreamEvent =
  | { type: 'step'; step: NlAgentStep }
  | { type: 'done'; user_message: ChatMessage; assistant_message: ChatMessage }
  | { type: 'error'; error: string };

@Injectable({ providedIn: 'root' })
export class ChatService {
  private readonly api = inject(ApiService);
  private readonly tokens = inject(TokenService);

  listSessions(includeInactive = false): Observable<ChatSessionListResponse> {
    return this.api.get<ChatSessionListResponse>('/kpi/chat/sessions', {
      include_inactive: includeInactive,
    });
  }

  createSession(title?: string): Observable<ChatSessionDetail> {
    return this.api.post<ChatSessionDetail>('/kpi/chat/sessions', { title });
  }

  getSession(id: number): Observable<ChatSessionDetail> {
    return this.api.get<ChatSessionDetail>(`/kpi/chat/sessions/${id}`);
  }

  renameSession(id: number, title: string): Observable<ChatSessionDetail> {
    return this.api.put<ChatSessionDetail>(`/kpi/chat/sessions/${id}`, { title });
  }

  deleteSession(id: number): Observable<{ deleted: boolean }> {
    return this.api.delete<{ deleted: boolean }>(`/kpi/chat/sessions/${id}`);
  }

  sendTurn(id: number, prompt: string): Observable<ChatTurnResponse> {
    return this.api.post<ChatTurnResponse>(`/kpi/chat/sessions/${id}/turn`, { prompt });
  }

  /**
   * Open a server-sent-events stream against ``/turn/stream`` and emit
   * each parsed event through the returned Observable. Uses ``fetch`` +
   * ``ReadableStream`` because EventSource doesn't support POST bodies
   * or the JWT Authorization header used by the rest of the app.
   *
   * Unsubscribing aborts the underlying fetch via AbortController, which
   * causes the backend's worker thread to drain on the next iteration
   * boundary (the ``finally`` in ``run_turn_streaming`` sets the cancel
   * event when the generator is abandoned).
   */
  sendTurnStream(id: number, prompt: string): Observable<ChatStreamEvent> {
    return new Observable<ChatStreamEvent>(subscriber => {
      const ctrl = new AbortController();
      this.runStream(id, prompt, subscriber, ctrl.signal).catch(err => {
        if (ctrl.signal.aborted) return;       // expected on unsubscribe
        subscriber.error(err);
      });
      return () => ctrl.abort();
    });
  }

  /**
   * Best-effort cancel for the in-flight streaming turn on this session.
   * Fire-and-forget — the SSE consumer also aborts on unsubscribe, which
   * is what really stops the UI from waiting; this just nudges the
   * backend to wind the worker down sooner instead of finishing the run.
   */
  cancelTurn(id: number): Observable<{ cancelled: boolean }> {
    return this.api.post<{ cancelled: boolean }>(
      `/kpi/chat/sessions/${id}/turn/cancel`, {},
    );
  }

  // -- internals ----------------------------------------------------------

  private async runStream(
    id: number,
    prompt: string,
    subscriber: Subscriber<ChatStreamEvent>,
    signal: AbortSignal,
  ): Promise<void> {
    const token = this.tokens.getAccessToken();
    const resp = await fetch(`${environment.apiUrl}/kpi/chat/sessions/${id}/turn/stream`, {
      method: 'POST',
      signal,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ prompt }),
    });

    if (!resp.ok || !resp.body) {
      const text = await resp.text().catch(() => '');
      throw new Error(text || `Stream HTTP ${resp.status}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    // SSE record delimiter is two newlines. Some proxies normalise to
    // \r\n\r\n, so we accept both — split on any double-newline.
    const RECORD_RE = /\r?\n\r?\n/;

    try {
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let parts = buffer.split(RECORD_RE);
        // Last fragment may be partial — keep it in the buffer.
        buffer = parts.pop() ?? '';
        for (const raw of parts) {
          const evt = this.parseSseRecord(raw);
          if (evt) subscriber.next(evt);
        }
      }
      // Flush any trailing complete record.
      if (buffer.trim()) {
        const evt = this.parseSseRecord(buffer);
        if (evt) subscriber.next(evt);
      }
      subscriber.complete();
    } finally {
      try { reader.releaseLock(); } catch { /* already released */ }
    }
  }

  private parseSseRecord(raw: string): ChatStreamEvent | null {
    // We only care about the ``data:`` line — the ``event:`` line is
    // duplicated inside the JSON payload's ``type`` field anyway, which
    // keeps the parser tolerant of fragmented SSE.
    let dataLine = '';
    for (const line of raw.split(/\r?\n/)) {
      if (line.startsWith('data:')) {
        dataLine += line.slice(5).trimStart();
      }
    }
    if (!dataLine) return null;
    try {
      return JSON.parse(dataLine) as ChatStreamEvent;
    } catch {
      return null;
    }
  }
}
