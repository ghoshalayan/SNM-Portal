import { ChangeDetectionStrategy, Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDividerModule } from '@angular/material/divider';
import { Tutorial, TUTORIALS, TutorialId } from './tutorial-content';

/**
 * Renders a structured tutorial guide in a modal. Content is sourced
 * from TUTORIALS in tutorial-content.ts — keep formatting changes in
 * this template only, content edits in that file.
 */
@Component({
  selector: 'app-tutorial-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatDividerModule,
  ],
  template: `
    <h2 mat-dialog-title class="title-row">
      <mat-icon class="title-icon">{{ tutorial.icon }}</mat-icon>
      <div class="title-text">
        <span class="title-main">{{ tutorial.title }}</span>
        <span class="title-sub">{{ tutorial.subtitle }}</span>
      </div>
      <button mat-icon-button mat-dialog-close aria-label="Close" class="close-btn">
        <mat-icon>close</mat-icon>
      </button>
    </h2>

    <mat-dialog-content class="content">
      <div class="breadcrumb">
        <mat-icon class="bc-icon">place</mat-icon>
        <ng-container *ngFor="let part of tutorial.whereToFind; let last = last">
          <span class="bc-part">{{ part }}</span>
          <mat-icon *ngIf="!last" class="bc-sep">chevron_right</mat-icon>
        </ng-container>
      </div>

      <section *ngFor="let s of tutorial.sections; let first = first" class="section">
        <mat-divider *ngIf="!first" class="section-divider"></mat-divider>
        <h3 class="section-heading">{{ s.heading }}</h3>
        <p *ngIf="s.intro" class="section-intro">{{ s.intro }}</p>
        <ol class="steps">
          <li *ngFor="let step of s.steps" class="step">
            <strong *ngIf="step.label">{{ step.label }}.</strong>
            <span class="step-body">{{ step.body }}</span>
          </li>
        </ol>
      </section>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-stroked-button mat-dialog-close>Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host { display: block; }

    .title-row {
      display: flex; align-items: flex-start; gap: 12px;
      margin: 0 !important;
      padding-right: 8px;
    }
    .title-icon {
      color: var(--snm-accent, #4a90e2);
      font-size: 28px; width: 28px; height: 28px;
      margin-top: 2px;
    }
    .title-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
    .title-main { font-size: 1.15rem; font-weight: 600; color: var(--snm-text-primary); }
    .title-sub { font-size: 0.82rem; color: var(--snm-text-muted); font-weight: 400; }
    .close-btn { margin-top: -4px; }

    .content {
      max-height: 70vh;
      min-width: 560px;
      max-width: 720px;
      padding-top: 8px !important;
    }

    .breadcrumb {
      display: flex; align-items: center; gap: 4px;
      padding: 6px 10px;
      margin-bottom: 16px;
      background: var(--snm-accent-subtle, rgba(74, 144, 226, 0.08));
      border-radius: 6px;
      font-size: 0.82rem;
      color: var(--snm-text-secondary);
    }
    .bc-icon { font-size: 16px; width: 16px; height: 16px; color: var(--snm-accent, #4a90e2); }
    .bc-sep { font-size: 14px; width: 14px; height: 14px; color: var(--snm-text-muted); }
    .bc-part { font-weight: 500; }

    .section { margin-bottom: 4px; }
    .section-divider { margin: 16px 0 12px; }
    .section-heading {
      margin: 0 0 6px;
      font-size: 1rem; font-weight: 600;
      color: var(--snm-text-primary);
    }
    .section-intro {
      margin: 0 0 10px;
      font-size: 0.88rem;
      line-height: 1.55;
      color: var(--snm-text-secondary);
    }

    .steps {
      margin: 0;
      padding-left: 20px;
      display: flex; flex-direction: column; gap: 8px;
    }
    .step {
      font-size: 0.88rem;
      line-height: 1.55;
      color: var(--snm-text-primary);
    }
    .step strong {
      color: var(--snm-accent-dark, var(--snm-accent, #1565c0));
      margin-right: 4px;
    }
    .step-body { color: var(--snm-text-secondary); }

    @media (max-width: 640px) {
      .content { min-width: 0; }
    }
  `],
})
export class TutorialDialogComponent {
  readonly tutorial: Tutorial;

  constructor(
    private dialogRef: MatDialogRef<TutorialDialogComponent>,
    @Inject(MAT_DIALOG_DATA) data: { id: TutorialId },
  ) {
    this.tutorial = TUTORIALS[data.id];
  }
}
