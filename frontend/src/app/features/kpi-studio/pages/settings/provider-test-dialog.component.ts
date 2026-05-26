/**
 * Result dialog for "Test connection" on a provider card.
 *
 * Shows every diagnostic field the backend returned — display name +
 * kind + base URL + model_used + response_model + latency + preview +
 * error. Crucial for the "is this hitting OpenAI or OpenRouter?"
 * question because the ``response_model`` field shows what the
 * upstream actually echoed back, which is the only definitive answer.
 */
import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA, MatDialogModule, MatDialogRef,
} from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

import { ProviderTestResponse } from '../../models/schema.types';

@Component({
  selector: 'app-provider-test-dialog',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatDialogModule, MatIconModule],
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="title-icon" [class.ok]="data.ok" [class.fail]="!data.ok">
        {{ data.ok ? 'check_circle' : 'error_outline' }}
      </mat-icon>
      Test result: {{ data.display_name }}
    </h2>
    <mat-dialog-content class="content">
      <div class="status" [class.ok]="data.ok" [class.fail]="!data.ok">
        {{ data.ok ? 'Round-trip succeeded.' : 'Round-trip failed.' }}
      </div>

      <dl class="detail">
        <dt>Provider kind</dt>
        <dd><code>{{ data.kind }}</code></dd>
        <dt>Base URL</dt>
        <dd><code>{{ data.base_url || '(default)' }}</code></dd>
        <dt>Model requested</dt>
        <dd><code>{{ data.model_used }}</code></dd>
        <dt *ngIf="data.response_model" class="echo-key">
          Model echoed back
          <mat-icon class="hint-ico"
                    title="This is the model name the upstream API confirmed it ran. If it differs from the requested model, the provider routed your request — e.g. OpenRouter may resolve aliases. If it shows a totally different vendor, you're hitting the wrong provider.">
            help_outline
          </mat-icon>
        </dt>
        <dd *ngIf="data.response_model"><code>{{ data.response_model }}</code></dd>
        <dt *ngIf="data.latency_ms !== null">Round-trip latency</dt>
        <dd *ngIf="data.latency_ms !== null">{{ data.latency_ms }} ms</dd>
        <dt *ngIf="data.response_preview">Response preview</dt>
        <dd *ngIf="data.response_preview">
          <code class="preview">{{ data.response_preview }}</code>
        </dd>
        <dt *ngIf="data.error">Error</dt>
        <dd *ngIf="data.error" class="err">
          <code>{{ data.error }}</code>
        </dd>
      </dl>

      <div class="diagnostic" *ngIf="mismatchSuspicion()">
        <mat-icon>warning</mat-icon>
        <div>
          The echoed model differs from what you requested. If this
          provider is OpenRouter, that's normal (it routes upstream).
          If it's not — you may be hitting a different service than
          intended. Check the Base URL above matches the provider
          kind's expected URL.
        </div>
      </div>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-raised-button color="primary" (click)="close()">Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    .title-icon { vertical-align: middle; margin-right: 6px; }
    .title-icon.ok { color: #2e7d32; }
    .title-icon.fail { color: #c62828; }
    .content {
      min-width: 480px;
      max-width: 92vw;
      padding-top: 4px;
    }
    .status {
      padding: 8px 12px; border-radius: 6px;
      font-weight: 600; margin-bottom: 14px;
      &.ok {
        background: rgba(46,125,50,0.10); color: #2e7d32;
        border: 1px solid rgba(46,125,50,0.35);
      }
      &.fail {
        background: rgba(229,57,53,0.10); color: #c62828;
        border: 1px solid rgba(229,57,53,0.40);
      }
    }
    dl.detail {
      display: grid; grid-template-columns: 180px 1fr;
      column-gap: 10px; row-gap: 6px;
      margin: 0;
      font-size: 13px;
    }
    dl.detail dt {
      color: var(--snm-text-muted);
      font-weight: 600;
    }
    dl.detail dd { margin: 0; color: var(--snm-text-primary); word-break: break-all; }
    dl.detail code {
      background: var(--snm-bg-panel);
      padding: 1px 6px;
      border-radius: 4px;
      font-family: monospace;
      font-size: 12px;
    }
    dl.detail code.preview { white-space: pre-wrap; display: inline-block; }
    .echo-key { display: inline-flex; align-items: center; gap: 4px; }
    .hint-ico { font-size: 14px; width: 14px; height: 14px; opacity: 0.7; cursor: help; }
    dd.err code { color: #c62828; }

    .diagnostic {
      display: flex; gap: 10px; align-items: flex-start;
      margin-top: 14px;
      padding: 10px 12px;
      border-radius: 6px;
      background: rgba(200,150,30,0.10);
      border: 1px solid rgba(200,150,30,0.40);
      color: var(--snm-text-secondary);
      font-size: 12px; line-height: 1.5;
      mat-icon { color: rgba(160,110,0,0.95); flex-shrink: 0; }
    }
  `],
})
export class ProviderTestDialogComponent {
  constructor(
    public dialogRef: MatDialogRef<ProviderTestDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: ProviderTestResponse,
  ) {}

  /** True when the requested model and echoed model differ — common
   *  for OpenRouter (which translates aliases) but suspicious for
   *  other providers. */
  mismatchSuspicion(): boolean {
    if (!this.data.ok || !this.data.response_model) return false;
    return this.data.response_model.toLowerCase() !==
           this.data.model_used.toLowerCase();
  }

  close(): void {
    this.dialogRef.close();
  }
}
