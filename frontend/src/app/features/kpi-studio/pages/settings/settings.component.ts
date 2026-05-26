/**
 * KPI Studio settings page — tabbed admin surface.
 *
 * Five tabs, one concern per tab:
 *  1. Providers       — multi-provider CRUD via card grid + dialog.
 *  2. Stage routing   — assign (provider, model) per pipeline stage.
 *  3. Agent caps      — token budget, max iterations, max tokens/call.
 *  4. Domain knowledge — admin-curated business context.
 *  5. Health          — per-provider probe state + recent scheduler runs.
 *
 * Backend storage:
 *  - kpi_llm_provider_config: one row per provider (added in
 *    n1o2p3q4r5s6_create_provider_configs.py).
 *  - kpi_settings.stage_models JSON: per-stage routing, values are
 *    {provider_config_id, model} after the 2026-05-25 refactor.
 *  - kpi_settings legacy columns: still readable as a fallback for
 *    rows the admin hasn't re-saved through the new UI yet.
 */
import {
  ChangeDetectionStrategy, Component, DestroyRef, OnInit,
  computed, inject, signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { forkJoin } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { SettingsService } from '../../services/settings.service';
import { ProvidersService } from '../../services/providers.service';
import { NotificationService } from '../../../../core/services/notification.service';
import {
  HealthcheckResponse,
  KpiSettings,
  KpiSettingsUpdate,
  ProviderConfig,
  ProviderKind,
  StageDefinition,
  StageRoutingEntry,
} from '../../models/schema.types';
import { FormattedError, formatHttpError } from '../../shared/error-format';
import { KpiErrorBannerComponent } from '../../shared/error-banner.component';
import { ProviderDialogComponent, ProviderDialogData } from './provider-dialog.component';
import { ProviderTestDialogComponent } from './provider-test-dialog.component';
import { CallLogTabComponent } from './call-log-tab.component';
import { ConfirmDialogComponent } from '../../../../shared/components/confirm-dialog/confirm-dialog.component';


/** Local form-shape per stage row. Two fields: which provider config
 *  to use + which model to send. Either may be blank — both blank
 *  means "fall through to default_stage_model → legacy single provider". */
interface StageRow {
  key: string;
  label: string;
  description: string;
  built: boolean;
  providerConfigId: number | null;
  model: string;
}


@Component({
  selector: 'app-kpi-settings',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    MatButtonModule, MatCardModule, MatChipsModule, MatDialogModule,
    MatDividerModule, MatFormFieldModule, MatIconModule, MatInputModule,
    MatProgressBarModule, MatProgressSpinnerModule, MatSelectModule,
    MatSlideToggleModule, MatTabsModule, MatTooltipModule,
    KpiErrorBannerComponent,
    CallLogTabComponent,
  ],
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
})
export class SettingsComponent implements OnInit {
  private readonly api = inject(SettingsService);
  private readonly providersSvc = inject(ProvidersService);
  private readonly notify = inject(NotificationService);
  private readonly dialog = inject(MatDialog);
  private readonly destroyRef = inject(DestroyRef);

  // ---- shell state ------------------------------------------------------
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly testing = signal<Record<number, boolean>>({});
  readonly loadError = signal<FormattedError | null>(null);
  readonly settings = signal<KpiSettings | null>(null);
  readonly providers = signal<ProviderConfig[]>([]);
  readonly providerKinds = signal<ProviderKind[]>(
    ['openai', 'openrouter', 'cerebras', 'ollama_cloud', 'azure_openai']);
  readonly activeTab = signal(0);

  // ---- agent caps ------------------------------------------------------
  readonly tokenBudgetField = signal<number | null>(null);
  readonly maxIterationsField = signal<number | null>(null);
  readonly maxTokensPerCallField = signal<number | null>(null);

  // ---- domain knowledge ------------------------------------------------
  readonly domainKnowledgeField = signal<string>('');
  readonly domainKnowledgeTouched = signal(false);

  // ---- stage routing ---------------------------------------------------
  readonly stageRows = signal<StageRow[]>([]);
  readonly defaultStageModelField = signal<string>('');

  // ---- automatic-healthcheck cost gate (2026-05-25) --------------------
  /** When false, PUT /settings skips probes (no rollback, no LLM cost
   *  on save) AND the weekly scheduled probe job no-ops. The manual
   *  "Run health check" button on this same tab still works — that's
   *  the explicit cost choice. */
  readonly healthcheckAutoField = signal(true);

  // ---- healthcheck -----------------------------------------------------
  readonly checking = signal(false);
  readonly healthcheck = signal<HealthcheckResponse | null>(null);

  // ---- persistent rollback banner --------------------------------------
  /** Set when the most recent save was rejected by the backend's
   *  healthcheck. Cleared on next successful save / explicit dismiss /
   *  fresh load. The toast disappears in 5s — this stays put so the
   *  admin can read which model failed without re-running the save. */
  readonly rollbackError = signal<{
    failures: string[];
    /** Stage keys parsed out of failures (best effort) so the Stage
     *  Routing tab can highlight the offending rows. */
    failedStages: string[];
  } | null>(null);

  // ---- derived ---------------------------------------------------------
  readonly activeProviders = computed(() =>
    this.providers().filter(p => p.is_active));

  readonly noProviders = computed(() => this.providers().length === 0);

  /** Provider id → stage health probe (used to colour matrix rows). */
  readonly stageHealth = computed<Record<string, { ok: boolean; error: string | null; latency: number | null }>>(() => {
    const out: Record<string, { ok: boolean; error: string | null; latency: number | null }> = {};
    const hc = this.healthcheck();
    if (!hc) return out;
    for (const probe of hc.probes) {
      for (const stage of probe.stages) {
        out[stage] = { ok: probe.ok, error: probe.error, latency: probe.latency_ms };
      }
    }
    return out;
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    forkJoin({
      settings: this.api.get(),
      providers: this.providersSvc.list(),
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ settings: s, providers }) => {
          this.settings.set(s);
          this.providers.set(providers.items);
          this.providerKinds.set(providers.kinds as ProviderKind[]);

          this.tokenBudgetField.set(s.token_budget);
          this.maxIterationsField.set(s.max_iterations);
          this.maxTokensPerCallField.set(s.max_tokens_per_call);
          this.domainKnowledgeField.set(s.domain_knowledge ?? '');
          this.domainKnowledgeTouched.set(false);
          this.defaultStageModelField.set(s.default_stage_model ?? '');
          this.healthcheckAutoField.set(s.healthcheck_auto_enabled);

          this.stageRows.set(this.buildStageRows(s));

          this.loading.set(false);
          // Auto-load probes only when the admin has opted in to
          // automatic healthchecks. Otherwise the Health tab shows
          // "no recent probe — click Run health check to fire one"
          // and zero LLM cost is incurred just by opening Settings.
          if (s.healthcheck_auto_enabled) {
            this.runHealthcheck(false);
          }
        },
        error: err => {
          this.loading.set(false);
          this.loadError.set(formatHttpError(err, 'Failed to load settings'));
        },
      });
  }

  private buildStageRows(s: KpiSettings): StageRow[] {
    const stages = s.stages || [];
    const sm = s.stage_models || {};
    return stages.map((stage: StageDefinition) => {
      const entry = sm[stage.key];
      let providerConfigId: number | null = null;
      let model = '';
      if (entry && typeof entry === 'object') {
        providerConfigId = (entry as any).provider_config_id ?? null;
        model = (entry as any).model ?? '';
      } else if (typeof entry === 'string') {
        // Legacy string format — no provider override; only model.
        model = entry;
      }
      return {
        key: stage.key,
        label: stage.label,
        description: stage.description,
        built: stage.built,
        providerConfigId,
        model,
      };
    });
  }

  // ---- providers tab ---------------------------------------------------

  openAddProvider(): void {
    const data: ProviderDialogData = {
      existing: null,
      kinds: this.providerKinds(),
    };
    const ref = this.dialog.open(ProviderDialogComponent,
      { data, width: '640px', maxWidth: '92vw' });
    ref.afterClosed().subscribe(saved => {
      if (saved) this.load();
    });
  }

  openEditProvider(p: ProviderConfig): void {
    const data: ProviderDialogData = {
      existing: p,
      kinds: this.providerKinds(),
    };
    const ref = this.dialog.open(ProviderDialogComponent,
      { data, width: '640px', maxWidth: '92vw' });
    ref.afterClosed().subscribe(saved => {
      if (saved) this.load();
    });
  }

  /** Promote a provider to system default via PUT /providers/{id}.
   *  Backend's update path auto-demotes the previous default, so this
   *  is a single round-trip; we reload to refresh both the cards
   *  ("default" pill moves) and the Stage Routing tab (placeholders
   *  read the new default's default_model). */
  makeDefault(p: ProviderConfig): void {
    if (p.is_default) return;
    this.providersSvc.update(p.provider_config_id, { is_default: true })
      .subscribe({
        next: () => {
          this.notify.success(`${p.display_name} is now the system default.`);
          this.load();
        },
        error: err => {
          this.notify.error(this.formatHttpDetail(err) || 'Couldn’t set default.');
        },
      });
  }

  toggleProviderActive(p: ProviderConfig): void {
    this.providersSvc.update(p.provider_config_id, { is_active: !p.is_active })
      .subscribe({
        next: () => {
          this.notify.success(
            p.is_active
              ? `Deactivated ${p.display_name}`
              : `Activated ${p.display_name}`,
          );
          this.load();
        },
        error: err => {
          this.notify.error(err?.error?.detail || 'Toggle failed');
        },
      });
  }

  confirmDeleteProvider(p: ProviderConfig): void {
    this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: `Delete ${p.display_name}?`,
        message: `This hard-deletes the provider config. Prefer Deactivate `
              + `if you may want it back. Stages still routed to this provider `
              + `will refuse the delete with a 409.`,
        confirmText: 'Delete',
        confirmColor: 'warn',
      },
    }).afterClosed().subscribe(ok => {
      if (!ok) return;
      this.providersSvc.delete(p.provider_config_id).subscribe({
        next: () => {
          this.notify.success(`Deleted ${p.display_name}`);
          this.load();
        },
        error: err => {
          this.notify.error(err?.error?.detail || 'Delete failed');
        },
      });
    });
  }

  testProvider(p: ProviderConfig, model?: string): void {
    this.testing.update(t => ({ ...t, [p.provider_config_id]: true }));
    this.providersSvc.test(p.provider_config_id, model).subscribe({
      next: result => {
        this.testing.update(t => {
          const copy = { ...t };
          delete copy[p.provider_config_id];
          return copy;
        });
        this.dialog.open(ProviderTestDialogComponent, {
          data: result, width: '640px', maxWidth: '92vw',
        });
      },
      error: err => {
        this.testing.update(t => {
          const copy = { ...t };
          delete copy[p.provider_config_id];
          return copy;
        });
        this.notify.error(err?.error?.detail || 'Test failed');
      },
    });
  }

  // ---- stage routing tab -----------------------------------------------

  onStageProviderChange(stageKey: string, providerConfigId: number | null): void {
    this.stageRows.update(rows => rows.map(r =>
      r.key === stageKey ? { ...r, providerConfigId } : r));
  }

  onStageModelChange(stageKey: string, model: string): void {
    this.stageRows.update(rows => rows.map(r =>
      r.key === stageKey ? { ...r, model } : r));
  }

  /** Lookup helper used by the template to render the provider name
   *  next to each stage's pill. */
  providerName(id: number | null): string {
    if (id == null) return '(default)';
    const p = this.providers().find(x => x.provider_config_id === id);
    return p?.display_name ?? `#${id} (missing)`;
  }

  effectiveStageModel(stageKey: string): string {
    return this.settings()?.effective_stage_models?.[stageKey] ?? '';
  }

  // ---- domain knowledge tab --------------------------------------------

  onDomainKnowledgeInput(v: string): void {
    this.domainKnowledgeField.set(v);
    this.domainKnowledgeTouched.set(true);
  }

  // ---- save (covers caps + stage routing + domain knowledge) -----------

  private buildPayload(force = false): KpiSettingsUpdate {
    const stageModels: Record<string, StageRoutingEntry> = {};
    for (const row of this.stageRows()) {
      const entry: { provider_config_id?: number; model?: string } = {};
      if (row.providerConfigId != null) {
        entry.provider_config_id = row.providerConfigId;
      }
      const m = row.model.trim();
      if (m) entry.model = m;
      if (entry.provider_config_id != null || entry.model) {
        stageModels[row.key] = entry;
      }
    }
    return {
      token_budget: this.tokenBudgetField(),
      max_iterations: this.maxIterationsField(),
      max_tokens_per_call: this.maxTokensPerCallField(),
      stage_models: stageModels,
      default_stage_model: this.defaultStageModelField() || null,
      healthcheck_auto_enabled: this.healthcheckAutoField(),
      force,
      ...(this.domainKnowledgeTouched()
        ? { domain_knowledge: this.domainKnowledgeField() }
        : {}),
    };
  }

  save(force = false): void {
    this.saving.set(true);
    this.api.update(this.buildPayload(force))
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: s => {
          this.settings.set(s);
          this.domainKnowledgeField.set(s.domain_knowledge ?? '');
          this.domainKnowledgeTouched.set(false);
          this.defaultStageModelField.set(s.default_stage_model ?? '');
          this.stageRows.set(this.buildStageRows(s));
          this.saving.set(false);
          this.rollbackError.set(null);  // clear stale failure banner
          this.notify.success('Settings saved.');
          // Same cost-gate: don't fire fresh probes after save when
          // the admin has opted out of automatic healthchecks.
          if (s.healthcheck_auto_enabled) {
            this.runHealthcheck(true);
          }
        },
        error: err => {
          this.saving.set(false);
          const detail = err?.error?.detail;
          if (detail?.code === 'healthcheck_failed') {
            const failures: string[] = detail.failures || [];
            // Best-effort parse: each failure string looks like
            // "<provider-label>/<model>: <error>". The Health probe
            // also returns a `stages` list per probe but the rollback
            // failures don't carry it; we re-fetch the healthcheck
            // below so the matrix can colour rows by name.
            this.rollbackError.set({
              failures,
              failedStages: [],
            });
            this.notify.error(
              `Save rolled back — ${failures.length} probe(s) failed. ` +
              `See the red banner.`,
            );
            // Jump to the Stage Routing tab so the user lands on the
            // surface where they can fix the offending models.
            this.activeTab.set(1);
            // Re-run healthcheck (uses cache flushed by the failed
            // PUT) so per-stage pills + the Health tab show the same
            // failures the rollback complained about. Don't toast on
            // this one — the banner is doing the talking.
            this.api.healthcheck(false).subscribe({
              next: hc => {
                this.healthcheck.set(hc);
                // Now we DO have per-stage info — fill in the
                // failedStages so the matrix can highlight rows.
                const failed = hc.probes
                  .filter(p => !p.ok)
                  .flatMap(p => p.stages);
                this.rollbackError.update(prev => prev
                  ? { ...prev, failedStages: [...new Set(failed)] }
                  : prev);
              },
            });
          } else {
            this.notify.error(this.formatHttpDetail(err) || 'Save failed');
            // Always log the raw error so the browser console has the
            // request id / stack when the toast scrolls away.
            console.error('[KpiSettings] save failed', err);
          }
        },
      });
  }

  /** Normalise the many shapes ``err.error.detail`` can take:
   *  - 422 Pydantic validation: ``[{loc, msg, type}, ...]``
   *  - 400 service ValueError:  string
   *  - 400 structured failure:  {code, message, ...}
   *  - 5xx / unknown:           empty body, status code only.
   *
   *  Returns a single human-readable line for the toast so the admin
   *  doesn't have to crack open DevTools to read "[object Object]". */
  private formatHttpDetail(err: any): string {
    const detail = err?.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((e: any) => {
          const loc = Array.isArray(e?.loc)
            ? e.loc.filter((p: any) => p !== 'body').join('.')
            : '';
          const msg = e?.msg || 'invalid';
          return loc ? `${loc}: ${msg}` : msg;
        })
        .join(' · ');
    }
    if (detail && typeof detail === 'object') {
      return detail.message || JSON.stringify(detail);
    }
    if (err?.status) {
      const txt = err.statusText ? ` ${err.statusText}` : '';
      return `HTTP ${err.status}${txt}`;
    }
    return '';
  }

  saveAnyway(): void { this.save(true); }

  dismissRollbackBanner(): void {
    this.rollbackError.set(null);
  }

  /** True when this stage row has a failing healthcheck probe — used
   *  to colour the row red so the admin can spot it without reading
   *  the banner failure list. */
  isStageFailing(stageKey: string): boolean {
    const h = this.stageHealth()[stageKey];
    if (!h) return false;
    return !h.ok;
  }

  stageFailureDetail(stageKey: string): string {
    const h = this.stageHealth()[stageKey];
    return h?.error || '';
  }

  // ---- health tab ------------------------------------------------------

  runHealthcheck(force: boolean): void {
    this.checking.set(true);
    this.api.healthcheck(force)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: hc => {
          this.healthcheck.set(hc);
          this.checking.set(false);
          if (force) {
            if (hc.overall_ok) {
              this.notify.success('All stage models responded.');
            } else {
              const failed = hc.probes.filter(p => !p.ok).length;
              this.notify.error(`${failed} stage model(s) failed the healthcheck.`);
            }
          }
        },
        error: () => this.checking.set(false),
      });
  }

  // ---- call-log tab callback ------------------------------------------

  /** Child Call log tab saved the logging toggles — sync our settings
   *  signal so the rest of the page (and any other tab) sees the
   *  fresh ``call_logging_enabled`` / ``call_log_retention_days``. */
  onCallLogSettingsSaved(s: KpiSettings): void {
    this.settings.set(s);
    this.healthcheckAutoField.set(s.healthcheck_auto_enabled);
  }

  // ---- misc UI helpers -------------------------------------------------

  kindLabel(k: ProviderKind | string): string {
    const map: Record<string, string> = {
      openai: 'OpenAI',
      openrouter: 'OpenRouter',
      cerebras: 'Cerebras',
      ollama_cloud: 'Ollama Cloud',
      azure_openai: 'Azure OpenAI',
    };
    return map[k] || k;
  }
}
