import {
  AfterViewChecked,
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  OnInit,
  ViewChild,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatMenuModule } from '@angular/material/menu';
import { MatChipsModule } from '@angular/material/chips';
import { MatTableModule } from '@angular/material/table';
import { MatDialog } from '@angular/material/dialog';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subscription } from 'rxjs';

import { ChatService, ChatStreamEvent } from '../../services/chat.service';
import { NotificationService } from '../../../../core/services/notification.service';
import {
  ChartConfig,
  ChatMessage,
  ChatSessionDetail,
  ChatSessionSummary,
  ExecutionResult,
  NlAgentStep,
} from '../../models/schema.types';
import { ConfirmDialogComponent } from '../../../../shared/components/confirm-dialog/confirm-dialog.component';
import { ChartRendererComponent } from '../chart-renderer/chart-renderer.component';
import {
  SaveAsKpiDialogComponent,
  SaveAsKpiResult,
} from './save-as-kpi-dialog.component';

@Component({
  selector: 'app-chat-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    MatButtonModule, MatIconModule, MatFormFieldModule, MatInputModule,
    MatProgressBarModule, MatTooltipModule, MatMenuModule, MatChipsModule,
    MatTableModule,
    ChartRendererComponent,
  ],
  templateUrl: './chat-panel.component.html',
  styleUrls: ['./chat-panel.component.scss'],
})
export class ChatPanelComponent implements OnInit, AfterViewChecked {
  private readonly chats = inject(ChatService);
  private readonly notify = inject(NotificationService);
  private readonly dialog = inject(MatDialog);
  private readonly destroyRef = inject(DestroyRef);

  /** Compact mode hides the sessions sidebar (useful for the
   * dashboard-docked side panel where space is tight). */
  readonly compact = input(false);

  // ---- state ------------------------------------------------------------
  readonly sessionsLoading = signal(false);
  readonly turnPending = signal(false);
  readonly sessions = signal<ChatSessionSummary[]>([]);
  readonly active = signal<ChatSessionDetail | null>(null);
  readonly composer = signal('');
  /** True when the user manually scrolled up — disables auto-scroll. */
  readonly stickToBottom = signal(true);
  /** Live-streamed agent steps for the current pending turn. Reset to []
   *  when a new turn starts; cleared on completion or stop. Backed by a
   *  signal so the template re-renders as steps land. */
  readonly liveSteps = signal<NlAgentStep[]>([]);

  /** Typing-effect state — when an assistant message is mid-reveal,
   *  ``typingMessageId`` is its id and ``typingText`` is the partial
   *  text accumulated so far. The template substitutes ``typingText``
   *  for ``m.content`` while the animation runs. */
  readonly typingMessageId = signal<number | null>(null);
  readonly typingText = signal<string>('');
  private typingTimer: ReturnType<typeof setInterval> | null = null;

  // ---- derived ----------------------------------------------------------
  readonly canSend = computed(
    () => this.composer().trim().length > 0 && !this.turnPending() && !!this.active(),
  );
  readonly messages = computed(() => this.active()?.messages ?? []);

  @ViewChild('messageList') private messageList?: ElementRef<HTMLElement>;
  private wantScroll = false;
  /** Held while a turn is in flight so the user can soft-cancel via stop().
   *  Backend keeps running; we just stop awaiting the response and re-sync
   *  by reloading the session. */
  private activeTurnSub: Subscription | null = null;

  constructor() {
    // Whenever the active session changes, scroll the message list to bottom.
    effect(() => {
      this.active(); // dependency
      this.wantScroll = true;
    });
  }

  ngOnInit(): void {
    this.loadSessions(/*selectFirst=*/true);
  }

  ngAfterViewChecked(): void {
    if (this.wantScroll && this.messageList && this.stickToBottom()) {
      // ``behavior: smooth`` keeps the scroll moving with the typing
      // animation rather than snapping each frame — the chat scrolls
      // gently downward as the response unfolds, ChatGPT-style.
      this.messageList.nativeElement.scrollTo({
        top: this.messageList.nativeElement.scrollHeight,
        behavior: 'smooth',
      });
      this.wantScroll = false;
    }
  }

  /** True when the given message is the one currently being typed out. */
  isTyping(m: ChatMessage): boolean {
    return m.role === 'assistant'
      && m.chat_message_id === this.typingMessageId();
  }

  /**
   * Reveal the assistant's explanation word-by-word into the message
   * bubble. Word granularity reads more naturally than per-character —
   * fast enough to feel responsive, slow enough to track. While the
   * animation runs we keep ``wantScroll = true`` so the smooth scroll
   * follows the growing text.
   */
  private startTypingAnimation(m: ChatMessage): void {
    this.cancelTypingAnimation();
    const full = m.content || '';
    if (!full) return;
    this.typingMessageId.set(m.chat_message_id);
    this.typingText.set('');

    // Tokenize into words + trailing whitespace so spacing is preserved.
    const tokens = full.match(/\S+\s*/g) ?? [full];
    let i = 0;
    this.typingTimer = setInterval(() => {
      if (i >= tokens.length) {
        this.cancelTypingAnimation();
        return;
      }
      this.typingText.update(t => t + tokens[i]);
      this.wantScroll = true;
      i += 1;
    }, 28);
  }

  private cancelTypingAnimation(): void {
    if (this.typingTimer) {
      clearInterval(this.typingTimer);
      this.typingTimer = null;
    }
    this.typingMessageId.set(null);
    this.typingText.set('');
  }

  /** Track whether the user has scrolled away from the bottom — when
   * they have, we stop auto-snapping so they can read history without
   * being yanked down on every new message (ChatGPT behaviour). */
  onMessagesScroll(event: Event): void {
    const el = event.target as HTMLElement;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    // 24px slack — small fluctuations from rendering shouldn't toggle the flag.
    this.stickToBottom.set(distanceFromBottom < 24);
  }

  // ---- session list -----------------------------------------------------

  loadSessions(selectFirst = false): void {
    this.sessionsLoading.set(true);
    this.chats.listSessions()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.sessions.set(res.items);
          this.sessionsLoading.set(false);
          if (selectFirst && res.items.length && !this.active()) {
            this.openSession(res.items[0].chat_session_id);
          }
        },
        error: err => {
          this.sessionsLoading.set(false);
          this.notify.error(err?.error?.detail ?? 'Could not load chat sessions');
        },
      });
  }

  openSession(id: number): void {
    // Switching sessions invalidates any in-flight typing animation —
    // the message it was animating is no longer in view.
    this.cancelTypingAnimation();
    this.chats.getSession(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: s => { this.active.set(s); this.wantScroll = true; },
        error: err => this.notify.error(err?.error?.detail ?? 'Could not open session'),
      });
  }

  newChat(): void {
    this.chats.createSession()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: s => {
          this.active.set(s);
          // Refresh the sidebar so the new (titled-Untitled-for-now) row appears.
          this.loadSessions();
        },
        error: err => this.notify.error(err?.error?.detail ?? 'Could not create session'),
      });
  }

  rename(s: ChatSessionSummary | ChatSessionDetail): void {
    const current = s.title ?? '';
    const next = window.prompt('Rename session', current);
    if (next == null || next.trim() === current) return;
    this.chats.renameSession(s.chat_session_id, next.trim())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: updated => {
          if (this.active()?.chat_session_id === updated.chat_session_id) {
            this.active.set(updated);
          }
          this.loadSessions();
        },
        error: err => this.notify.error(err?.error?.detail ?? 'Rename failed'),
      });
  }

  confirmDelete(s: ChatSessionSummary): void {
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Delete chat?',
        message: `"${s.title || 'Untitled chat'}" will be soft-deleted. History stays in the audit log.`,
        confirmText: 'Delete',
      },
    });
    ref.afterClosed()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(ok => {
        if (!ok) return;
        this.chats.deleteSession(s.chat_session_id).subscribe({
          next: () => {
            if (this.active()?.chat_session_id === s.chat_session_id) {
              this.active.set(null);
            }
            this.loadSessions(/*selectFirst=*/true);
          },
          error: err => this.notify.error(err?.error?.detail ?? 'Delete failed'),
        });
      });
  }

  // ---- composer ---------------------------------------------------------

  send(): void {
    if (!this.canSend()) return;
    const sess = this.active();
    if (!sess) return;
    const prompt = this.composer().trim();
    this.turnPending.set(true);

    // Optimistic: append the user message immediately so the UI doesn't
    // feel laggy while the agent runs (could take 5-10s).
    const stamp = new Date().toISOString();
    const optimistic: ChatMessage = {
      chat_message_id: -1,
      chat_session_id: sess.chat_session_id,
      role: 'user',
      content: prompt,
      succeeded: true,
      tokens: 0,
      duration_ms: 0,
      created_at: stamp,
    };
    this.active.set({ ...sess, messages: [...sess.messages, optimistic] });
    this.wantScroll = true;
    this.composer.set('');

    // Reset the live timeline; it'll fill in as `step` events arrive.
    this.liveSteps.set([]);

    this.activeTurnSub = this.chats.sendTurnStream(sess.chat_session_id, prompt)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (evt: ChatStreamEvent) => this.handleStreamEvent(evt),
        error: err => {
          this.turnPending.set(false);
          this.activeTurnSub = null;
          this.liveSteps.set([]);
          this.notify.error(err?.message ?? err?.error?.detail ?? 'Send failed');
          // Drop the optimistic user message — the turn never landed.
          const current = this.active();
          if (current) {
            this.active.set({
              ...current,
              messages: current.messages.filter(m => m.chat_message_id !== -1),
            });
          }
        },
      });
  }

  /** Apply a single SSE event from the streaming endpoint to local state. */
  private handleStreamEvent(evt: ChatStreamEvent): void {
    if (evt.type === 'step') {
      this.liveSteps.update(prev => [...prev, evt.step]);
      this.wantScroll = true;
      return;
    }
    if (evt.type === 'done') {
      this.turnPending.set(false);
      this.activeTurnSub = null;
      this.liveSteps.set([]);
      const current = this.active();
      if (!current) return;
      const withoutOptimistic = current.messages.filter(m => m.chat_message_id !== -1);
      this.active.set({
        ...current,
        messages: [...withoutOptimistic, evt.user_message, evt.assistant_message],
      });
      this.wantScroll = true;
      this.loadSessions();
      // Kick off the typing animation on the assistant explanation —
      // the surrounding content (SQL block, chart, table, insights) all
      // appear at once around the typing text.
      this.startTypingAnimation(evt.assistant_message);
      return;
    }
    if (evt.type === 'error') {
      this.turnPending.set(false);
      this.activeTurnSub = null;
      this.liveSteps.set([]);
      this.notify.error(evt.error || 'Send failed');
      const current = this.active();
      if (current) {
        this.active.set({
          ...current,
          messages: current.messages.filter(m => m.chat_message_id !== -1),
        });
      }
    }
  }

  /**
   * Cancel the in-flight turn — both client- and server-side. The cancel
   * call signals the backend's worker thread (which polls between agent
   * iterations); the unsubscribe drops the SSE consumer; reloading the
   * session pulls whatever the backend actually persisted so the UI is
   * always consistent with stored history.
   */
  stop(): void {
    if (!this.turnPending()) return;
    const sess = this.active();
    // Fire the cancel POST first so the worker has a chance to bail out
    // before its next LLM round; then drop the SSE consumer.
    if (sess) {
      this.chats.cancelTurn(sess.chat_session_id)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({ error: () => {} });  // best-effort, silent
    }
    this.activeTurnSub?.unsubscribe();
    this.activeTurnSub = null;
    this.turnPending.set(false);
    this.liveSteps.set([]);
    this.cancelTypingAnimation();
    if (sess) {
      this.openSession(sess.chat_session_id);
    }
    this.notify.info('Stopped — re-synced with the server.');
  }

  onComposerKey(event: KeyboardEvent): void {
    // Enter sends; Shift+Enter inserts a newline. Standard chat UX.
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  // ---- view helpers -----------------------------------------------------

  /** Map ChatMessage.result_columns + result_rows into Mat-table-friendly
   * row objects for inline rendering. Capped at 10 rows so a huge
   * result doesn't blow up the chat panel; user can drill in later. */
  rowsAsObjects(m: ChatMessage): Record<string, any>[] {
    if (!m.result_columns || !m.result_rows) return [];
    return m.result_rows.slice(0, 10).map(row => {
      const obj: Record<string, any> = {};
      m.result_columns!.forEach((c, i) => { obj[c] = row[i]; });
      return obj;
    });
  }

  truncationNote(m: ChatMessage): string | null {
    if (!m.result_rows) return null;
    if (m.result_rows.length > 10) {
      return `Showing 10 of ${m.result_rows.length} rows.`;
    }
    return null;
  }

  /** Concise step label for the agent timeline. */
  stepLabel(s: NlAgentStep): string {
    // Pre-flight Planner / Resolver steps — the user sees these first.
    if (s.type === 'planner_question') return 'Planner — checking scope';
    if (s.type === 'resolver_answer') {
      if (s.tool === 'lookup_domain') return 'Resolver — Knowledge Hub lookup';
      if (s.tool === 'find_table')    return 'Resolver — schema lookup';
      if (s.tool === 'find_column')   return 'Resolver — column lookup';
      if (s.tool === 'finalize')      return 'Planner — verdict';
      return 'Resolver';
    }
    if (s.tool) return this.humaniseTool(s.tool);
    if (s.type === 'thought') return 'Reasoning';
    if (s.type === 'final')   return 'Final answer';
    if (s.type === 'abort')   return s.error === 'cancelled_by_user' ? 'Stopped' : 'Aborted';
    return s.type;
  }

  /** Material icon name that matches the step kind. Same icon set the
   *  rest of the app already uses; no extra dependencies. */
  stepIcon(s: NlAgentStep): string {
    if (s.type === 'planner_question') return 'troubleshoot';
    if (s.type === 'resolver_answer') {
      if (s.tool === 'lookup_domain') return 'menu_book';
      if (s.tool === 'find_table')    return 'table_view';
      if (s.tool === 'find_column')   return 'view_column';
      if (s.tool === 'finalize')      return 'fact_check';
      return 'search';
    }
    if (s.type === 'tool_error') return 'error_outline';
    if (s.type === 'thought')    return 'psychology';
    if (s.type === 'final')      return 'check_circle';
    if (s.type === 'abort')      return 'cancel';
    if (s.tool === 'list_tables')          return 'table_view';
    if (s.tool === 'describe_table')       return 'view_list';
    if (s.tool === 'peek_distinct_values') return 'travel_explore';
    if (s.tool === 'validate_sql')         return 'rule_folder';
    if (s.tool === 'propose_sql')          return 'flag';
    return 'bolt';
  }

  /** One-line context appended below the step label — e.g. which table
   *  the agent is inspecting. Returns empty when nothing useful to show. */
  stepDetail(s: NlAgentStep): string {
    if (s.error) return s.error;
    const args = s.args || {};
    const table = (args as any)['table'] || (args as any)['table_name'];
    if (table) return `${table}`;
    if (s.type === 'thought' && typeof s.output === 'string') {
      return (s.output as string).slice(0, 140);
    }
    return '';
  }

  /** Tooltip-friendly tool label (snake_case → "Title Case"). */
  private humaniseTool(name: string): string {
    return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  /** What to show on the pulsing tail row — narrates what the agent is
   *  doing right now based on the most recent emitted step. */
  pendingTail(): string {
    const steps = this.liveSteps();
    if (steps.length === 0) return 'Agent is thinking…';
    const last = steps[steps.length - 1];
    if (last.type === 'planner_question') return 'Planner is checking the question…';
    if (last.type === 'resolver_answer' && last.tool === 'finalize') return 'Planning the query…';
    if (last.type === 'resolver_answer') return 'Reading context…';
    if (last.type === 'final') return 'Wrapping up…';
    if (last.type === 'abort') return 'Stopping…';
    if (last.tool === 'propose_sql') return 'Validating SQL…';
    if (last.tool) return `Continuing after ${this.humaniseTool(last.tool)}…`;
    return 'Agent is thinking…';
  }

  trackStep = (i: number, _: NlAgentStep) => i;

  /** Synthesise an ExecutionResult shape for the existing
   * ChartRendererComponent so it can render the chart inline without
   * a separate input contract. */
  asExecutionResult(m: ChatMessage): ExecutionResult | null {
    if (!m.result_columns || !m.result_rows) return null;
    return {
      columns: m.result_columns,
      rows: m.result_rows,
      row_count: m.result_rows.length,
      truncated: false,
      duration_ms: m.duration_ms,
      rewritten_sql: m.rewritten_sql ?? '',
      notes: [],
      suggestion: null,
    };
  }

  /** Whether to render a chart in this assistant bubble. Hidden when:
   *   - there's no chart_config (failed turn / table-only result), or
   *   - chart_config.type is "table" (the inline mat-table already covers it). */
  hasChart(m: ChatMessage): boolean {
    return !!m.chart_config
      && m.chart_config.type !== 'table'
      && !!m.result_columns?.length;
  }

  /** Whether to surface "Save as KPI" — only on assistant turns that
   * produced executable SQL successfully. Saves don't require chart_config
   * since the editor will pick a default. */
  canSaveAsKpi(m: ChatMessage): boolean {
    return m.role === 'assistant' && !!m.sql && m.succeeded;
  }

  saveAsKpi(m: ChatMessage): void {
    if (!this.canSaveAsKpi(m)) return;
    this.dialog.open(SaveAsKpiDialogComponent, {
      width: '560px',
      maxWidth: '92vw',
      data: {
        sql: m.sql!,
        chart_config: (m.chart_config as ChartConfig | null) ?? null,
        // Default name from the first line of the assistant's explanation
        // — keeps the modal pre-filled with something sensible.
        defaultName: (m.content || 'KPI').split('\n')[0].slice(0, 200),
      } satisfies { sql: string; chart_config: ChartConfig | null; defaultName: string },
    });
    // The dialog handles its own success/error notifications + nav.
  }

  /** B3 — clicking a suggested follow-up drops it into the composer.
   * Don't auto-send: the user often wants to tweak the wording first. */
  useRecommendation(text: string): void {
    if (!text) return;
    this.composer.set(text);
  }

  trackSession = (_: number, s: ChatSessionSummary) => s.chat_session_id;
  trackMessage = (_: number, m: ChatMessage) => m.chat_message_id;
}

// Re-export the dialog result type so callers don't have to import
// from the dialog module directly.
export type { SaveAsKpiResult };
