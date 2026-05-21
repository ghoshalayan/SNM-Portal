import {
  Component, EventEmitter, Input, OnChanges, OnInit, Output, SimpleChanges,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';

import { HasPermissionDirective } from '../../../shared/directives/has-permission.directive';
import { CycleService, OrderCycle } from '../services/cycle.service';
import { NotificationService } from '../../../core/services/notification.service';

/** Horizontal pill strip showing every cycle on a quotation, with a
 *  "Start New Call-off" CTA at the end. Clicking a pill emits
 *  ``cycleSelected`` so the parent (Stage-2 panel) can re-fetch the
 *  bundle. Selection state is owned by the parent — this component
 *  just renders.
 *
 *  Loads its own data via ``CycleService.list()`` so the host doesn't
 *  have to plumb cycle arrays through @Inputs. Re-loads when
 *  ``quotId`` changes; the parent can also force a reload by calling
 *  ``reload()`` after a mutation. */
@Component({
  selector: 'app-cycle-selector',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule, MatIconModule, MatTooltipModule, MatSlideToggleModule,
    HasPermissionDirective,
  ],
  template: `
    <div class="cycle-strip" *ngIf="cycles.length > 0 || showStartButton">
      <span class="cycle-strip-label">Call-off cycles:</span>
      <button
        *ngFor="let c of cycles"
        type="button"
        class="cycle-pill"
        [class.active]="c.quotOrderCycleId === selectedCycleId"
        [class.status-active]="c.status === 'Active'"
        [class.status-complete]="c.status === 'Complete'"
        [class.status-abandoned]="c.status === 'Abandoned'"
        (click)="onPillClick(c)"
        [matTooltip]="tooltipFor(c)"
        matTooltipPosition="above"
      >
        <mat-icon class="status-icon">{{ iconFor(c.status) }}</mat-icon>
        <span>Cycle {{ c.cycleNo }}</span>
      </button>

      <ng-container *ngIf="showStartButton">
        <button
          type="button"
          mat-stroked-button color="primary" class="start-cycle-btn"
          (click)="onStartClick()"
          *hasPermission="'Quotations:canStartNewCycle'"
        >
          <mat-icon>add_circle_outline</mat-icon>
          Start New Call-off
        </button>
      </ng-container>

      <mat-slide-toggle
        *ngIf="hasAnyAbandoned"
        class="show-abandoned-toggle"
        [checked]="includeAbandoned"
        (change)="onToggleAbandoned($event.checked)"
      >
        Show abandoned
      </mat-slide-toggle>
    </div>
  `,
  styles: [`
    .cycle-strip {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      padding: 8px 12px;
      background: var(--snm-bg-panel);
      border: 1px solid var(--snm-border-divider);
      border-radius: 8px;
      margin-bottom: 12px;
    }
    .cycle-strip-label {
      font-size: 0.85rem;
      color: var(--snm-text-secondary);
      margin-right: 4px;
    }
    .cycle-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      border-radius: 20px;
      border: 1px solid var(--snm-border-divider);
      background: var(--snm-bg-card);
      color: var(--snm-text-primary);
      font-size: 0.9rem;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .cycle-pill:hover {
      border-color: var(--snm-accent);
      background: var(--snm-accent-shadow);
    }
    .cycle-pill.active {
      border-color: var(--snm-accent);
      background: var(--snm-accent);
      color: white;
    }
    .cycle-pill.status-complete .status-icon { color: #2e7d32; }
    .cycle-pill.status-abandoned {
      opacity: 0.6;
      text-decoration: line-through;
    }
    .cycle-pill.status-abandoned .status-icon { color: var(--snm-text-faint); }
    .cycle-pill.status-active .status-icon { color: var(--snm-accent); }
    .cycle-pill.active .status-icon { color: white; }
    .status-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
    }
    .start-cycle-btn {
      margin-left: auto;
    }
    .show-abandoned-toggle {
      margin-left: 8px;
      font-size: 0.85rem;
    }
  `],
})
export class CycleSelectorComponent implements OnInit, OnChanges {
  /** Parent quotation. */
  @Input({ required: true }) quotId!: number;

  /** Currently-selected cycle id; parent owns this state and passes it
   *  back in so the active pill renders correctly. */
  @Input() selectedCycleId: number | null = null;

  /** When true, show the "Start New Call-off" button (gated client-side
   *  by ``CanStartNewCycle``). Parent disables this when the quotation
   *  isn't in a status that allows new cycles. */
  @Input() showStartButton = true;

  /** Emitted when the user clicks a pill. Parent should re-fetch the
   *  cycle bundle for the new id. */
  @Output() cycleSelected = new EventEmitter<OrderCycle>();

  /** Emitted when the user clicks "Start New Call-off". Parent owns the
   *  confirmation dialog + API call so it can run optimistic updates. */
  @Output() startNewCycle = new EventEmitter<void>();

  /** Emitted after every successful list refresh — lets the parent
   *  auto-select cycle #1 on first load, or the latest cycle on
   *  reload after a mutation. */
  @Output() cyclesLoaded = new EventEmitter<OrderCycle[]>();

  cycles: OrderCycle[] = [];
  loading = false;
  includeAbandoned = false;
  hasAnyAbandoned = false;

  constructor(
    private cycleService: CycleService,
    private notifications: NotificationService,
  ) {}

  ngOnInit(): void {
    if (this.quotId) this.reload();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['quotId'] && !changes['quotId'].firstChange) {
      this.reload();
    }
  }

  /** Re-fetch the cycle list. Call after any mutation (start / close /
   *  abandon / append-PO) so the strip stays in sync. */
  reload(): void {
    if (!this.quotId) return;
    this.loading = true;
    this.cycleService.list(this.quotId, this.includeAbandoned).subscribe({
      next: (resp) => {
        this.cycles = resp.cycles;
        this.hasAnyAbandoned = resp.cycles.some(c => c.status === 'Abandoned')
          || this.includeAbandoned;
        this.cyclesLoaded.emit(resp.cycles);
        this.loading = false;
      },
      error: (e) => {
        this.notifications.error(
          e?.error?.message || e?.error?.detail || 'Failed to load cycles.',
        );
        this.loading = false;
      },
    });
  }

  onPillClick(c: OrderCycle): void {
    if (c.quotOrderCycleId === this.selectedCycleId) return;
    this.cycleSelected.emit(c);
  }

  onStartClick(): void {
    this.startNewCycle.emit();
  }

  onToggleAbandoned(checked: boolean): void {
    this.includeAbandoned = checked;
    this.reload();
  }

  tooltipFor(c: OrderCycle): string {
    const started = c.startedOn ? new Date(c.startedOn).toLocaleDateString() : '?';
    if (c.status === 'Active') return `Cycle ${c.cycleNo} · Active · started ${started}`;
    const closed = c.closedOn ? new Date(c.closedOn).toLocaleDateString() : '?';
    return `Cycle ${c.cycleNo} · ${c.status} · ${started} → ${closed}`;
  }

  iconFor(status: OrderCycle['status']): string {
    switch (status) {
      case 'Active': return 'play_circle_outline';
      case 'Complete': return 'check_circle_outline';
      case 'Abandoned': return 'cancel';
    }
  }
}
