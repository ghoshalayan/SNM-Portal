import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  output,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatIconModule } from '@angular/material/icon';
import {
  CHART_THEMES,
  ChartStyle,
  ChartTheme,
} from '../../models/schema.types';

const DEFAULT_STYLE: ChartStyle = { theme: 'default', animations: true };

@Component({
  selector: 'app-chart-style-picker',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    MatFormFieldModule, MatSelectModule, MatSlideToggleModule, MatIconModule,
  ],
  template: `
    <div class="picker">
      <mat-form-field appearance="outline" class="theme">
        <mat-label>Theme</mat-label>
        <mat-select [value]="theme()" (valueChange)="onThemeChange($event)">
          <mat-select-trigger>
            <span class="trigger-row">
              <span class="swatch" [style.background]="themeSwatch(theme())"></span>
              {{ themeLabel(theme()) }}
            </span>
          </mat-select-trigger>
          <mat-option *ngFor="let t of themes" [value]="t.value">
            <span class="trigger-row">
              <span class="swatch" [style.background]="t.preview"></span>
              {{ t.label }}
            </span>
          </mat-option>
        </mat-select>
      </mat-form-field>

      <mat-slide-toggle [checked]="animations()"
                        (change)="onAnimChange($event.checked)"
                        matTooltip="Card-enter and bar-grow animations">
        <span class="anim-label">
          <mat-icon class="anim-icon">animation</mat-icon>
          Animations
        </span>
      </mat-slide-toggle>
    </div>
  `,
  styles: [`
    .picker {
      display: flex; gap: 8px; align-items: center; flex-wrap: nowrap;
    }
    .theme { flex: 1 1 0; min-width: 0; }
    .theme ::ng-deep .mat-mdc-form-field-subscript-wrapper { display: none; }
    .trigger-row { display: inline-flex; align-items: center; gap: 8px; }
    .swatch {
      display: inline-block;
      width: 14px; height: 14px;
      border-radius: 3px;
      border: 1px solid var(--snm-border-divider, #ccc);
    }
    .anim-label { display: inline-flex; align-items: center; gap: 4px; }
    .anim-icon { font-size: 16px; width: 16px; height: 16px; }
    /* Compact the slide toggle so the Theme dropdown gets the bulk
       of the row width. */
    mat-slide-toggle .anim-label { font-size: 0.82rem; }
  `],
})
export class ChartStylePickerComponent {
  readonly themes = CHART_THEMES;
  readonly value = input<ChartStyle | null>(null);
  readonly styleChange = output<ChartStyle>();

  readonly theme = computed<ChartTheme>(
    () => (this.value()?.theme as ChartTheme) || DEFAULT_STYLE.theme!,
  );
  /** ``true`` by default — falsy only when explicitly set to ``false``. */
  readonly animations = computed(
    () => this.value()?.animations !== false,
  );

  onThemeChange(t: ChartTheme): void {
    this.styleChange.emit({
      theme: t,
      animations: this.animations(),
    });
  }

  onAnimChange(on: boolean): void {
    this.styleChange.emit({
      theme: this.theme(),
      animations: on,
    });
  }

  themeLabel(t: ChartTheme): string {
    return CHART_THEMES.find(x => x.value === t)?.label ?? 'Default';
  }

  themeSwatch(t: ChartTheme): string {
    return CHART_THEMES.find(x => x.value === t)?.preview ?? '#4a90e2';
  }
}
