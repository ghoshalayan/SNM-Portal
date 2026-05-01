import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-skeleton-loader',
  standalone: true,
  imports: [CommonModule],
  template: `
    @switch (type) {
      @case ('table') {
        <div class="skeleton-table">
          <!-- Header row -->
          <div class="skeleton-table-row skeleton-header-row">
            @for (col of colArray; track $index) {
              <div class="skeleton-cell"></div>
            }
          </div>
          <!-- Data rows -->
          @for (row of rowArray; track $index) {
            <div class="skeleton-table-row">
              @for (col of colArray; track $index) {
                <div class="skeleton-cell"></div>
              }
            </div>
          }
        </div>
      }
      @case ('menu') {
        @for (item of rowArray; track $index) {
          <div class="skeleton-menu-item" [style.padding-left.px]="$index % 3 === 0 ? 20 : 48">
            @if ($index % 3 === 0) {
              <div class="skeleton-menu-icon"></div>
            }
            <div class="skeleton-menu-label" [style.width.%]="55 + ($index * 7) % 30"></div>
          </div>
        }
      }
      @case ('toolbar') {
        <div class="skeleton-toolbar">
          <div class="skeleton-button" style="width: 36px; height: 36px; border-radius: 50%;"></div>
          <div style="flex: 1"></div>
          <div class="skeleton-button" style="width: 160px; height: 32px;"></div>
          <div class="skeleton-text" style="width: 100px; height: 14px; margin: 0 1rem;"></div>
          <div class="skeleton-button" style="width: 36px; height: 36px; border-radius: 50%;"></div>
        </div>
      }
      @default {
        @for (item of rowArray; track $index) {
          <div class="skeleton-text" [style.width.%]="60 + ($index * 13) % 35"></div>
        }
      }
    }
  `,
  styles: [`
    :host { display: block; }

    .skeleton-table {
      width: 100%;
    }

    .skeleton-header-row {
      background: var(--snm-skeleton-header);
    }

    .skeleton-toolbar {
      display: flex;
      align-items: center;
      padding: 0 16px;
      height: 64px;
      gap: 8px;
    }
  `],
})
export class SkeletonLoaderComponent {
  @Input() type: 'table' | 'menu' | 'toolbar' | 'text' = 'text';
  @Input() rows = 5;
  @Input() columns = 4;

  get rowArray(): number[] {
    return Array(this.rows);
  }

  get colArray(): number[] {
    return Array(this.columns);
  }
}
