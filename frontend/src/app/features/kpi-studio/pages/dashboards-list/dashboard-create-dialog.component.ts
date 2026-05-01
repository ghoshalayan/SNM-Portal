import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatRadioModule } from '@angular/material/radio';
import { DashboardCreateRequest, DashboardScope } from '../../models/schema.types';

@Component({
  selector: 'app-dashboard-create-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule, MatButtonModule, MatDialogModule,
    MatFormFieldModule, MatInputModule, MatRadioModule,
  ],
  template: `
    <h2 mat-dialog-title>New dashboard</h2>
    <mat-dialog-content>
      <mat-form-field appearance="outline" class="full">
        <mat-label>Name</mat-label>
        <input matInput [ngModel]="name()" (ngModelChange)="name.set($event)"
               maxlength="200" required cdkFocusInitial>
      </mat-form-field>
      <mat-form-field appearance="outline" class="full">
        <mat-label>Description (optional)</mat-label>
        <textarea matInput rows="2" maxlength="1000"
                  [ngModel]="description()"
                  (ngModelChange)="description.set($event)"></textarea>
      </mat-form-field>

      <mat-radio-group [value]="scope()" (change)="scope.set($event.value)" class="scope-radio">
        <mat-radio-button value="user">
          <strong>Private</strong> — only you see it
        </mat-radio-button>
        <mat-radio-button value="company">
          <strong>Shared</strong> — everyone in your company sees it
        </mat-radio-button>
      </mat-radio-group>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button [mat-dialog-close]="null">Cancel</button>
      <button mat-flat-button color="primary"
              [disabled]="!name().trim()"
              (click)="confirm()">
        Create
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .full { width: 100%; }
    .scope-radio { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
  `],
})
export class DashboardCreateDialogComponent {
  readonly name = signal('');
  readonly description = signal('');
  readonly scope = signal<DashboardScope>('user');

  constructor(private readonly ref: MatDialogRef<DashboardCreateDialogComponent>) {}

  confirm(): void {
    const payload: DashboardCreateRequest = {
      name: this.name().trim(),
      description: this.description().trim() || null,
      scope: this.scope(),
    };
    this.ref.close(payload);
  }
}
