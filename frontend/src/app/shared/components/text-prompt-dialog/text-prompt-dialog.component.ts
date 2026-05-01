import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';

export interface TextPromptDialogData {
  title: string;
  label?: string;
  placeholder?: string;
  initial?: string;
  hint?: string;
  confirmText?: string;
  cancelText?: string;
}

/**
 * Tiny generic text-input prompt dialog. Returns the trimmed string on
 * confirm or `null` on cancel/empty. Shared so callers don't duplicate
 * MatDialog plumbing for one-shot text input flows like
 * "type a Specific Length" in the viability inline editor.
 */
@Component({
  selector: 'app-text-prompt-dialog',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatDialogModule,
    MatFormFieldModule, MatInputModule, MatButtonModule,
  ],
  template: `
    <h2 mat-dialog-title>{{ data.title }}</h2>
    <mat-dialog-content class="dialog-content">
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>{{ data.label || 'Value' }}</mat-label>
        <input matInput [(ngModel)]="value"
          [placeholder]="data.placeholder || ''"
          (keydown.enter)="confirm()" cdkFocusInitial />
        <mat-hint *ngIf="data.hint">{{ data.hint }}</mat-hint>
      </mat-form-field>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>{{ data.cancelText || 'Cancel' }}</button>
      <button mat-raised-button color="primary" (click)="confirm()" [disabled]="!value.trim()">
        {{ data.confirmText || 'OK' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .dialog-content { padding-top: 12px !important; min-width: 360px; }
    .full-width { width: 100%; }
  `],
})
export class TextPromptDialogComponent {
  value: string;

  constructor(
    public dialogRef: MatDialogRef<TextPromptDialogComponent, string | null>,
    @Inject(MAT_DIALOG_DATA) public data: TextPromptDialogData,
  ) {
    this.value = data.initial || '';
  }

  confirm(): void {
    const trimmed = (this.value || '').trim();
    this.dialogRef.close(trimmed || null);
  }
}
