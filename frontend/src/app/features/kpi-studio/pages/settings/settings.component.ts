import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatChipsModule } from '@angular/material/chips';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { SettingsService } from '../../services/settings.service';
import { NotificationService } from '../../../../core/services/notification.service';
import {
  KEEP_API_KEY,
  KpiSettings,
  KpiSettingsUpdate,
  SettingsTestResult,
} from '../../models/schema.types';
import { FormattedError, formatHttpError } from '../../shared/error-format';
import { KpiErrorBannerComponent } from '../../shared/error-banner.component';

@Component({
  selector: 'app-kpi-settings',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    MatButtonModule, MatIconModule, MatFormFieldModule, MatInputModule,
    MatSelectModule, MatSlideToggleModule, MatProgressBarModule,
    MatTooltipModule, MatChipsModule,
    KpiErrorBannerComponent,
  ],
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
})
export class SettingsComponent implements OnInit {
  private readonly api = inject(SettingsService);
  private readonly notify = inject(NotificationService);
  private readonly destroyRef = inject(DestroyRef);

  // ---- state ------------------------------------------------------------
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly testing = signal(false);
  readonly loadError = signal<FormattedError | null>(null);
  readonly settings = signal<KpiSettings | null>(null);
  readonly testResult = signal<SettingsTestResult | null>(null);

  // ---- form fields (signals so the template can two-way bind) ----------
  readonly providerField = signal<string>('');
  readonly modelField = signal<string>('');
  readonly baseUrlField = signal<string>('');
  /** When the user types here, it's a *new* key. Empty string = clear.
   * Initial state is empty (we never receive the stored key from the API). */
  readonly apiKeyField = signal<string>('');
  readonly apiKeyTouched = signal(false);
  readonly tokenBudgetField = signal<number | null>(null);
  readonly maxIterationsField = signal<number | null>(null);
  readonly maxTokensPerCallField = signal<number | null>(null);
  /** System Knowledge Hub — admin-curated business context. */
  readonly domainKnowledgeField = signal<string>('');
  readonly domainKnowledgeTouched = signal(false);
  /** Show / hide the API-key text. */
  readonly revealKey = signal(false);

  // ---- derived ----------------------------------------------------------
  readonly isUsingEnvFallback = computed(() => !!this.settings()?.using_env_fallback);
  readonly effectiveHasKey = computed(() => !!this.settings()?.effective_has_key);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.api.get()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: s => {
          this.settings.set(s);
          // Pre-fill form fields with stored values (NOT effective ones —
          // we want to show what's in the DB row, with placeholders for
          // any field that's currently env-fallback).
          this.providerField.set(s.llm_provider ?? '');
          this.modelField.set(s.openai_model ?? '');
          this.baseUrlField.set(s.openai_base_url ?? '');
          this.tokenBudgetField.set(s.token_budget);
          this.maxIterationsField.set(s.max_iterations);
          this.maxTokensPerCallField.set(s.max_tokens_per_call);
          this.domainKnowledgeField.set(s.domain_knowledge ?? '');
          this.domainKnowledgeTouched.set(false);
          // The API-key input always starts empty; user types a new key
          // to overwrite, leaves blank to keep the existing one.
          this.apiKeyField.set('');
          this.apiKeyTouched.set(false);
          this.loading.set(false);
        },
        error: err => {
          this.loading.set(false);
          this.loadError.set(formatHttpError(err, 'Failed to load settings'));
        },
      });
  }

  /** Build the PUT payload using the KEEP sentinel for the API key
   * when the user hasn't typed in it. */
  private buildPayload(): KpiSettingsUpdate {
    return {
      llm_provider: this.providerField() || null,
      openai_model: this.modelField() || null,
      openai_base_url: this.baseUrlField() || null,
      openai_api_key: this.apiKeyTouched() ? this.apiKeyField() : KEEP_API_KEY,
      token_budget: this.tokenBudgetField(),
      max_iterations: this.maxIterationsField(),
      max_tokens_per_call: this.maxTokensPerCallField(),
      // Only include when the user actually edited the field — keeps the
      // backend's "None means leave alone" semantics intact for users
      // who only tweaked LLM settings.
      ...(this.domainKnowledgeTouched()
        ? { domain_knowledge: this.domainKnowledgeField() }
        : {}),
    };
  }

  save(): void {
    this.saving.set(true);
    this.api.update(this.buildPayload())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: s => {
          this.settings.set(s);
          this.apiKeyField.set('');
          this.apiKeyTouched.set(false);
          this.domainKnowledgeField.set(s.domain_knowledge ?? '');
          this.domainKnowledgeTouched.set(false);
          this.saving.set(false);
          this.notify.success('Settings saved.');
        },
        error: err => {
          this.saving.set(false);
          this.notify.error(
            err?.error?.detail?.message ?? err?.error?.detail ?? 'Save failed',
          );
        },
      });
  }

  test(): void {
    this.testing.set(true);
    this.testResult.set(null);
    this.api.test()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: r => {
          this.testResult.set(r);
          this.testing.set(false);
        },
        error: err => {
          this.testing.set(false);
          this.testResult.set({
            ok: false,
            message: err?.error?.detail ?? 'Test request failed.',
          });
        },
      });
  }

  onApiKeyInput(v: string): void {
    this.apiKeyField.set(v);
    this.apiKeyTouched.set(true);
  }

  clearApiKey(): void {
    // User wants to clear — type empty string + mark touched.
    this.apiKeyField.set('');
    this.apiKeyTouched.set(true);
  }

  toggleReveal(): void {
    this.revealKey.update(v => !v);
  }

  onDomainKnowledgeInput(v: string): void {
    this.domainKnowledgeField.set(v);
    this.domainKnowledgeTouched.set(true);
  }
}
