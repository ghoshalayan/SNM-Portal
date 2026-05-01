import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { FormattedError } from './error-format';

@Component({
  selector: 'app-kpi-error-banner',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatButtonModule, MatIconModule],
  template: `
    <div class="error-banner" *ngIf="error() as e">
      <mat-icon>error_outline</mat-icon>
      <div class="content">
        <pre>{{ e.detail }}</pre>
      </div>
      <button mat-stroked-button color="primary"
              *ngIf="showRetry()"
              (click)="retry.emit()">
        <mat-icon>refresh</mat-icon>
        Retry
      </button>
      <button mat-icon-button (click)="dismiss.emit()" matTooltip="Dismiss">
        <mat-icon>close</mat-icon>
      </button>
    </div>
  `,
  styles: [`
    .error-banner {
      display: flex; gap: 12px; padding: 12px 16px;
      background: rgba(229, 57, 53, 0.08);
      border: 1px solid var(--snm-error, #e53935);
      border-radius: 6px; color: var(--snm-text-primary);
      align-items: flex-start;
      margin-bottom: 12px;
    }
    .error-banner > mat-icon {
      color: var(--snm-error, #e53935); flex-shrink: 0; margin-top: 2px;
    }
    .content { flex: 1; min-width: 0; }
    .content pre {
      margin: 0; font-family: inherit; font-size: 0.85rem;
      white-space: pre-wrap; word-break: break-word;
      color: var(--snm-text-primary);
    }
  `],
})
export class KpiErrorBannerComponent {
  readonly error = input<FormattedError | null>(null);
  readonly showRetry = input(true);
  readonly retry = output<void>();
  readonly dismiss = output<void>();
}
