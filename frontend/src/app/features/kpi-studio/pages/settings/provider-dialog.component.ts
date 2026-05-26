/**
 * Create-or-edit dialog for one KpiLlmProviderConfig.
 *
 * Single dialog covers both modes via ``data.existing``:
 *   null     → "Add provider", POST /settings/providers on save.
 *   present  → "Edit provider", PUT /settings/providers/{id} on save.
 *
 * The kind dropdown auto-fills base_url + a placeholder model so an
 * admin who picks "OpenRouter" gets a working starting point without
 * having to know the magic URL by heart.
 */
import { CommonModule } from '@angular/common';
import { Component, Inject, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA, MatDialogModule, MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';

import { NotificationService } from '../../../../core/services/notification.service';
import {
  KEEP_API_KEY,
  ProviderConfig,
  ProviderConfigCreate,
  ProviderConfigUpdate,
  ProviderKind,
} from '../../models/schema.types';
import { ProvidersService } from '../../services/providers.service';

export interface ProviderDialogData {
  existing: ProviderConfig | null;
  /** Allowed kinds — echoed by the backend on the providers list call. */
  kinds: ProviderKind[];
}

/** Per-kind metadata for the dropdown + auto-fill defaults. Mirrors
 *  the backend KIND_DEFAULTS map. Frontend-side so the form can
 *  pre-fill without an extra round-trip. */
const KIND_META: Record<ProviderKind, {
  label: string;
  baseUrl: string;
  defaultModel: string;
  hint: string;
}> = {
  openai: {
    label: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    defaultModel: 'gpt-5.4-nano',
    hint: 'Model names: gpt-5.4-nano, gpt-5.4, gpt-4o-mini, gpt-4o, etc.',
  },
  openrouter: {
    label: 'OpenRouter (one key, many models)',
    baseUrl: 'https://openrouter.ai/api/v1',
    defaultModel: 'anthropic/claude-3.5-sonnet',
    hint: 'Models: anthropic/claude-3.5-sonnet, openai/gpt-4o, google/gemini-flash-1.5, …',
  },
  cerebras: {
    label: 'Cerebras (OpenAI-compatible)',
    baseUrl: 'https://api.cerebras.ai/v1',
    defaultModel: 'llama-3.3-70b',
    hint: 'Models: llama-3.3-70b, llama-3.3-8b, etc.',
  },
  ollama_cloud: {
    label: 'Ollama Cloud (OpenAI-compatible)',
    baseUrl: 'https://ollama.com/v1',
    defaultModel: 'llama3.3',
    hint: 'Models follow the Ollama tag scheme: llama3.3, qwen2.5, …',
  },
  azure_openai: {
    label: 'Azure OpenAI',
    baseUrl: '',
    defaultModel: 'gpt-4o',
    hint: 'Base URL must be your full Azure resource URL (e.g. https://my-resource.openai.azure.com/openai/v1).',
  },
};

@Component({
  selector: 'app-provider-dialog',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    MatButtonModule, MatDialogModule, MatFormFieldModule,
    MatIconModule, MatInputModule, MatProgressSpinnerModule,
    MatSelectModule, MatSlideToggleModule, MatTooltipModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="title-icon">cloud_sync</mat-icon>
      {{ data.existing ? 'Edit provider' : 'Add provider' }}
    </h2>

    <mat-dialog-content class="content">
      <div class="row">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
          <mat-label>Kind</mat-label>
          <mat-select [value]="kindField()" (valueChange)="onKindChange($event)"
                      [disabled]="!!data.existing">
            <mat-option *ngFor="let k of data.kinds" [value]="k">
              {{ kindMeta[k]?.label || k }}
            </mat-option>
          </mat-select>
          <mat-hint *ngIf="kindMeta[kindField()]">
            {{ kindMeta[kindField()].hint }}
          </mat-hint>
          <mat-hint *ngIf="!!data.existing">
            Kind can't change after creation — delete + re-add to switch.
          </mat-hint>
        </mat-form-field>
      </div>

      <div class="row">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
          <mat-label>Display name</mat-label>
          <input matInput required maxlength="200"
                 [ngModel]="displayName()"
                 (ngModelChange)="displayName.set($event)"
                 placeholder="Production OpenRouter">
          <mat-hint>Admin label shown in stage-routing dropdowns + Provider cards.</mat-hint>
        </mat-form-field>
      </div>

      <div class="row">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
          <mat-label>API key</mat-label>
          <input matInput required
                 [type]="reveal() ? 'text' : 'password'"
                 [ngModel]="apiKey()"
                 (ngModelChange)="apiKey.set($event)"
                 [placeholder]="data.existing?.has_api_key
                   ? 'Stored key (hidden — type a new value to overwrite)'
                   : 'sk-...'"
                 autocomplete="off">
          <button mat-icon-button matSuffix type="button"
                  (click)="reveal.set(!reveal())"
                  [matTooltip]="reveal() ? 'Hide' : 'Reveal'">
            <mat-icon>{{ reveal() ? 'visibility_off' : 'visibility' }}</mat-icon>
          </button>
          <mat-hint *ngIf="data.existing?.has_api_key && !apiKey()">
            Existing key kept. Type a new value to overwrite.
          </mat-hint>
        </mat-form-field>
      </div>

      <div class="row">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
          <mat-label>Default model</mat-label>
          <input matInput required maxlength="200"
                 [ngModel]="defaultModel()"
                 (ngModelChange)="defaultModel.set($event); defaultModelTouched.set(true)"
                 [placeholder]="kindMeta[kindField()]?.defaultModel || ''">
          <mat-hint>
            Used by stage routing when a stage's Model field is left blank.
            Pre-filled from the kind's recommended model; edit as needed.
          </mat-hint>
        </mat-form-field>
      </div>

      <div class="row">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
          <mat-label>Base URL (optional)</mat-label>
          <input matInput
                 [ngModel]="baseUrl()"
                 (ngModelChange)="baseUrl.set($event)"
                 [placeholder]="defaultBaseUrl()">
          <mat-hint>
            Blank uses the kind default ({{ defaultBaseUrl() || '— none —' }}).
          </mat-hint>
        </mat-form-field>
      </div>

      <div class="row default-row">
        <mat-slide-toggle
          [checked]="isDefault()"
          (change)="isDefault.set($event.checked)"
          [disabled]="data.existing?.is_default === true && !isDefault()">
          <strong>Set as system default</strong>
        </mat-slide-toggle>
        <div class="default-hint">
          The default provider is used by every stage that leaves its
          Provider dropdown blank, with this provider's <strong>Default model</strong>
          as the fallback. Exactly one provider is default at any time —
          turning this ON automatically demotes the current default.
          <span *ngIf="data.existing?.is_default" class="muted">
            (This is currently the system default; toggle another provider
            to default to switch it off here.)
          </span>
        </div>
      </div>

      <ng-container *ngIf="kindField() === 'openrouter'">
        <div class="row">
          <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
            <mat-label>App URL (HTTP-Referer)</mat-label>
            <input matInput
                   [ngModel]="openrouterReferer()"
                   (ngModelChange)="openrouterReferer.set($event)"
                   placeholder="https://snm-portal.example.com/kpi-studio">
            <mat-hint>OpenRouter routing-fairness header.</mat-hint>
          </mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
            <mat-label>App name (X-Title)</mat-label>
            <input matInput
                   [ngModel]="openrouterAppName()"
                   (ngModelChange)="openrouterAppName.set($event)"
                   placeholder="SNM Portal KPI Studio">
          </mat-form-field>
        </div>
      </ng-container>

      <div class="row">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
          <mat-label>Description (optional)</mat-label>
          <input matInput maxlength="500"
                 [ngModel]="description()"
                 (ngModelChange)="description.set($event)"
                 placeholder="Who owns this key, rate-limit notes, etc.">
        </mat-form-field>
      </div>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button (click)="cancel()" [disabled]="saving()">Cancel</button>
      <button mat-raised-button color="primary"
              (click)="save()"
              [disabled]="saving() || !canSave()">
        <mat-spinner *ngIf="saving()" diameter="16" class="cta-spinner"></mat-spinner>
        {{ data.existing ? 'Save' : 'Create' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .title-icon { vertical-align: middle; margin-right: 6px; color: var(--snm-accent); }
    .content {
      display: flex; flex-direction: column; gap: 10px;
      min-width: 520px; max-width: 92vw;
      padding-top: 6px;
    }
    .row { display: flex; gap: 10px; flex-wrap: wrap; }
    .grow { flex: 1 1 auto; min-width: 220px; }
    .cta-spinner {
      display: inline-block; margin-right: 6px; vertical-align: middle;
    }
    .default-row {
      flex-direction: column; gap: 6px;
      padding: 10px 12px;
      border-radius: 8px;
      background: var(--snm-bg-panel);
      border: 1px solid var(--snm-border-divider);
    }
    .default-hint {
      font-size: 12px;
      color: var(--snm-text-muted);
      line-height: 1.45;
    }
    .muted { color: var(--snm-text-muted); }
  `],
})
export class ProviderDialogComponent {
  private readonly svc = inject(ProvidersService);
  private readonly notify = inject(NotificationService);

  readonly kindMeta = KIND_META;
  readonly saving = signal(false);
  readonly reveal = signal(false);
  readonly kindField = signal<ProviderKind>('openai');

  // Form fields as signals — computed() above reads them, and signal
  // reads is the ONLY thing computed() tracks for reactivity. A plain
  // class field here would freeze `canSave` at its first-evaluation
  // value (false) and the Create button would never enable no matter
  // what the user types.
  readonly displayName = signal('');
  readonly apiKey = signal('');
  readonly defaultModel = signal('');
  readonly defaultModelTouched = signal(false);
  readonly baseUrl = signal('');
  readonly openrouterReferer = signal('');
  readonly openrouterAppName = signal('');
  readonly description = signal('');
  readonly isDefault = signal(false);

  readonly canSave = computed(() => {
    const hasName = !!this.displayName().trim();
    const editMode = !!this.data.existing;
    const hasKey = editMode ? true : !!this.apiKey().trim();
    const hasModel = !!this.defaultModel().trim();
    return hasName && hasKey && hasModel;
  });

  constructor(
    public dialogRef: MatDialogRef<ProviderDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: ProviderDialogData,
  ) {
    if (data.existing) {
      const e = data.existing;
      this.kindField.set(e.kind);
      this.displayName.set(e.display_name);
      this.defaultModel.set(e.default_model || KIND_META[e.kind]?.defaultModel || '');
      this.baseUrl.set(e.base_url ?? '');
      this.openrouterReferer.set(e.openrouter_referer ?? '');
      this.openrouterAppName.set(e.openrouter_app_name ?? '');
      this.description.set(e.description ?? '');
      this.isDefault.set(!!e.is_default);
      // apiKey stays empty — empty + KEEP sentinel preserves stored value.
    } else {
      // Default to first allowed kind so the auto-fills make sense.
      const first = data.kinds[0] ?? 'openai';
      this.kindField.set(first as ProviderKind);
      // Force-fill default_model on create so the required field is
      // satisfied the moment the dialog opens. onKindChange below
      // only refreshes it on subsequent kind changes (and respects
      // a user edit via defaultModelTouched).
      const initMeta = KIND_META[first as ProviderKind];
      if (initMeta) {
        this.baseUrl.set(initMeta.baseUrl);
        this.defaultModel.set(initMeta.defaultModel);
      }
    }
  }

  defaultBaseUrl(): string {
    return KIND_META[this.kindField()]?.baseUrl ?? '';
  }

  /** When the user picks a kind, auto-fill base_url + default model
   *  if the form is otherwise empty. Doesn't overwrite values the
   *  user already typed. */
  onKindChange(next: ProviderKind): void {
    const prev = this.kindField();
    this.kindField.set(next);
    if (prev === next) return;
    const meta = KIND_META[next];
    if (!meta) return;
    // Only auto-fill when the current value matches the previous
    // kind's default — that way a user who pasted a custom URL keeps it.
    const prevMeta = KIND_META[prev];
    if (!this.baseUrl().trim() || this.baseUrl() === prevMeta?.baseUrl) {
      this.baseUrl.set(meta.baseUrl);
    }
    // Same logic for default model: leave the field alone once the
    // admin has typed in it (defaultModelTouched). Otherwise swap to
    // the new kind's recommended model so the form stays usable.
    if (!this.defaultModelTouched()) {
      this.defaultModel.set(meta.defaultModel);
    }
    if (next !== 'openrouter') {
      this.openrouterReferer.set('');
      this.openrouterAppName.set('');
    }
  }

  save(): void {
    if (!this.canSave()) return;
    this.saving.set(true);

    if (this.data.existing) {
      const payload: ProviderConfigUpdate = {
        display_name: this.displayName().trim(),
        api_key: this.apiKey().trim() || KEEP_API_KEY,
        default_model: this.defaultModel().trim(),
        base_url: this.baseUrl().trim() || null,
        openrouter_referer: this.openrouterReferer().trim() || null,
        openrouter_app_name: this.openrouterAppName().trim() || null,
        description: this.description().trim() || null,
      };
      // Only send is_default when it differs — and never send `false`
      // for the row that's already default (the backend would demote
      // it and pick a new fallback, which is rarely what the admin
      // intended on a plain Save). The disabled-toggle in the template
      // also blocks this path.
      const wasDefault = !!this.data.existing.is_default;
      if (this.isDefault() && !wasDefault) {
        payload.is_default = true;
      }
      this.svc.update(this.data.existing.provider_config_id, payload).subscribe({
        next: row => this.onSaved(row, 'updated'),
        error: err => this.onError(err),
      });
    } else {
      const payload: ProviderConfigCreate = {
        kind: this.kindField(),
        display_name: this.displayName().trim(),
        api_key: this.apiKey().trim(),
        default_model: this.defaultModel().trim(),
        base_url: this.baseUrl().trim() || null,
        openrouter_referer: this.openrouterReferer().trim() || null,
        openrouter_app_name: this.openrouterAppName().trim() || null,
        description: this.description().trim() || null,
        is_default: this.isDefault(),
      };
      this.svc.create(payload).subscribe({
        next: row => this.onSaved(row, 'created'),
        error: err => this.onError(err),
      });
    }
  }

  private onSaved(row: ProviderConfig, verb: 'created' | 'updated'): void {
    this.saving.set(false);
    this.notify.success(`Provider ${verb}: ${row.display_name}`);
    this.dialogRef.close(row);
  }

  private onError(err: any): void {
    this.saving.set(false);
    // The backend returns 400 with { detail: "..." } for service-level
    // ValueErrors, 422 with { detail: [{loc, msg, ...}, ...] } for
    // Pydantic validation, or our global error boundary's shape
    // { detail: { code, message, requestId } } for unexpected errors.
    // Format each loud enough that "click Create, nothing happens"
    // becomes "click Create, see exactly why".
    const detail = err?.error?.detail;
    let message = 'Save failed';
    if (typeof detail === 'string') {
      message = detail;
    } else if (Array.isArray(detail)) {
      message = detail
        .map((e: any) => `${(e.loc || []).join('.')}: ${e.msg}`)
        .join(' · ');
    } else if (detail && typeof detail === 'object') {
      message = detail.message || JSON.stringify(detail);
    } else if (err?.status) {
      message = `HTTP ${err.status}${err.statusText ? ' ' + err.statusText : ''}`;
    }
    this.notify.error(message);
    // Also log the full error so the browser console has the
    // request-id / stack for debugging when the toast scrolls away.
    console.error('[ProviderDialog] save failed', err);
  }

  cancel(): void {
    this.dialogRef.close(null);
  }
}
