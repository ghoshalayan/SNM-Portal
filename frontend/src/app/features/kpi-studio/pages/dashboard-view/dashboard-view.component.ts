import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  OnInit,
  ViewChild,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatChipsModule } from '@angular/material/chips';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDialog } from '@angular/material/dialog';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DashboardService } from '../../services/dashboard.service';
import { KpiService } from '../../services/kpi.service';
import { NotificationService } from '../../../../core/services/notification.service';
import {
  DashboardDetail,
  DashboardItem,
  KpiSummary,
} from '../../models/schema.types';
import { KpiCardComponent } from '../../components/kpi-card/kpi-card.component';
import { ConfirmDialogComponent } from '../../../../shared/components/confirm-dialog/confirm-dialog.component';
import { AddKpiDialogComponent } from './add-kpi-dialog.component';
import {
  ManageAssigneesDialogComponent,
  ManageAssigneesDialogData,
} from './manage-assignees-dialog.component';
import { FormattedError, formatHttpError } from '../../shared/error-format';
import { KpiErrorBannerComponent } from '../../shared/error-banner.component';
import { AuthService } from '../../../../core/auth/auth.service';

@Component({
  selector: 'app-dashboard-view',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    MatButtonModule, MatIconModule, MatProgressBarModule,
    MatChipsModule, MatTooltipModule,
    KpiCardComponent, KpiErrorBannerComponent,
  ],
  template: `
    <div class="page" *ngIf="dashboard() as d; else loadingTpl">
      <header class="page-header">
        <button mat-icon-button (click)="back()" matTooltip="Back to list">
          <mat-icon>arrow_back</mat-icon>
        </button>
        <div class="title-block">
          <h1>{{ d.name }}</h1>
          <p class="subtitle">
            <mat-chip class="scope-chip" [class.shared]="d.scope === 'company'" disabled>
              {{ d.scope === 'company' ? 'shared' : 'private' }}
            </mat-chip>
            {{ d.items.length }} card{{ d.items.length === 1 ? '' : 's' }} ·
            updated {{ d.updated_at | date:'short' }}
          </p>
        </div>
        <span class="spacer"></span>

        <ng-container *ngIf="!editMode(); else editingHead">
          <button mat-stroked-button (click)="reloadAll()" matTooltip="Refresh all cards">
            <mat-icon>refresh</mat-icon>
            Refresh
          </button>
          <button mat-flat-button color="primary" (click)="enterEdit()">
            <mat-icon>edit</mat-icon>
            Edit layout
          </button>
        </ng-container>
        <ng-template #editingHead>
          <button *ngIf="canManageAssignees()"
                  mat-stroked-button
                  (click)="openAssigneesDialog()"
                  matTooltip="Grant access to roles or users">
            <mat-icon>group</mat-icon>
            Manage Assignees
          </button>
          <button mat-stroked-button (click)="openAddKpi()">
            <mat-icon>add</mat-icon>
            Add KPI
          </button>
          <button mat-stroked-button (click)="compactLayout()"
                  matTooltip="Pull every tile up to remove empty rows">
            <mat-icon>compress</mat-icon>
            Compact up
          </button>
          <button mat-stroked-button color="primary"
                  (click)="autoDecorate()"
                  [disabled]="decorating() || !draftItems().length"
                  matTooltip="Add icons, animations, and per-card filters. Layout stays as-is — use Compact-up to tidy that.">
            <mat-icon>auto_awesome</mat-icon>
            {{ decorating() ? 'Polishing…' : 'AI Polish' }}
          </button>
          <button mat-stroked-button color="warn" (click)="cancelEdit()">
            Cancel
          </button>
          <button mat-flat-button color="primary" (click)="saveLayout()" [disabled]="!dirty()">
            <mat-icon>save</mat-icon>
            Save layout
          </button>
        </ng-template>
      </header>

      <p class="description" *ngIf="d.description">{{ d.description }}</p>

      <app-kpi-error-banner [error]="loadError()"
                             (retry)="reloadAll()"
                             (dismiss)="loadError.set(null)" />

      <mat-progress-bar *ngIf="loading()" mode="indeterminate"></mat-progress-bar>

      <!-- Power BI–style 12-column grid. Drag tiles by their header,
           resize via the bottom-right corner handle. Edit mode gates
           both interactions; read-only mode still places everything
           by saved coords but freezes the layout. -->
      <div *ngIf="d.items.length; else emptyTpl"
           #gridEl
           class="dash-grid"
           [class.editing]="editMode()"
           [style.--row-h.px]="rowHeight">
        <div *ngFor="let it of orderedItems(); let i = index; trackBy: trackItem"
             class="dash-tile"
             [class.dragging]="draggingItemId() === it.item_id"
             [style.--gx]="it.grid_x"
             [style.--gy]="it.grid_y"
             [style.--gw]="it.grid_w"
             [style.--gh]="it.grid_h"
             [style.animation-delay.ms]="i * 60"
             (pointerdown)="onTilePointerDown($event, it)">
          <app-kpi-card [item]="it"
                        [editable]="editMode()"
                        [showResize]="false"
                        (remove)="confirmRemove(it)" />
          <!-- Bottom-right resize grip — visible only in edit mode. -->
          <span *ngIf="editMode()"
                class="resize-grip"
                (pointerdown)="onResizePointerDown($event, it)"
                matTooltip="Drag to resize">
            <mat-icon>open_in_full</mat-icon>
          </span>
        </div>
        <!-- Ghost preview during drag/resize. -->
        <div *ngIf="ghost() as g" class="ghost"
             [style.--gx]="g.x"
             [style.--gy]="g.y"
             [style.--gw]="g.w"
             [style.--gh]="g.h"></div>
      </div>

      <ng-template #emptyTpl>
        <div class="empty">
          <mat-icon>dashboard</mat-icon>
          <p>This dashboard has no KPI cards yet.</p>
          <button mat-flat-button color="primary" (click)="enterEdit()" *ngIf="!editMode()">
            Add cards
          </button>
          <button mat-flat-button color="primary" (click)="openAddKpi()" *ngIf="editMode()">
            Add KPI
          </button>
        </div>
      </ng-template>
    </div>

    <ng-template #loadingTpl>
      <mat-progress-bar mode="indeterminate"></mat-progress-bar>
    </ng-template>
  `,
  styles: [`
    .page { padding: 16px 24px 24px; display: flex; flex-direction: column;
            gap: 12px; min-height: 100%; box-sizing: border-box; }
    .page-header { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    .page-header h1 { margin: 0; font-size: 1.4rem; color: var(--snm-text-primary); }
    .page-header .subtitle {
      margin: 2px 0 0; font-size: 0.8rem; color: var(--snm-text-muted);
      display: flex; align-items: center; gap: 6px;
    }
    .title-block { display: flex; flex-direction: column; }
    .scope-chip { font-size: 0.65rem; }
    .scope-chip.shared {
      background: rgba(74, 144, 226, 0.12);
      color: var(--snm-accent);
    }
    .spacer { flex: 1; }
    .description { margin: 0; color: var(--snm-text-secondary); font-size: 0.9rem; }

    /* Native 12-column CSS Grid. No transforms anywhere on the tile
       container, so translucent glass surfaces composite cleanly on
       top of the page background — same look as the welcome strip. */
    .dash-grid {
      position: relative;
      display: grid;
      grid-template-columns: repeat(24, 1fr);
      grid-auto-rows: var(--row-h, 40px);
      gap: 12px;
      width: 100%;
      min-height: 200px;
    }
    .dash-tile {
      position: relative;
      grid-column: calc(var(--gx) + 1) / span var(--gw);
      grid-row:    calc(var(--gy) + 1) / span var(--gh);
      min-width: 0;
      display: flex;
      animation: dash-tile-enter 420ms cubic-bezier(0.2, 0, 0, 1) both;
    }
    @keyframes dash-tile-enter {
      from { opacity: 0; transform: translateY(10px) scale(0.985); }
      to   { opacity: 1; transform: none; }
    }
    .dash-tile > app-kpi-card { flex: 1; min-width: 0; }
    .dash-grid.editing .dash-tile { cursor: grab; }
    .dash-grid.editing .dash-tile:active { cursor: grabbing; }
    .dash-tile.dragging {
      opacity: 0.55;
      pointer-events: none;
    }

    /* Bottom-right resize grip — only renders in edit mode. */
    .resize-grip {
      position: absolute;
      right: 4px; bottom: 4px;
      width: 22px; height: 22px;
      display: flex; align-items: center; justify-content: center;
      cursor: nwse-resize;
      border-radius: 4px;
      color: var(--snm-text-muted);
      background: transparent;
      transition: background 160ms ease, color 160ms ease;
      z-index: 2;
      mat-icon {
        font-size: 14px; width: 14px; height: 14px;
        transform: rotate(90deg);
      }
      &:hover {
        background: var(--snm-accent-subtle, rgba(91, 143, 217, 0.12));
        color: var(--snm-accent, #4a90e2);
      }
    }

    /* Ghost preview — dashed outline of the future cell during a
       drag or resize. Sits inside the same grid so its placement is
       just "render at these coords". */
    .ghost {
      grid-column: calc(var(--gx) + 1) / span var(--gw);
      grid-row:    calc(var(--gy) + 1) / span var(--gh);
      border: 2px dashed var(--snm-accent, #4a90e2);
      background: var(--snm-accent-subtle, rgba(91, 143, 217, 0.10));
      border-radius: 12px;
      pointer-events: none;
    }

    @media (max-width: 768px) {
      .dash-grid {
        grid-template-columns: 1fr;
        grid-auto-rows: minmax(280px, auto);
      }
      .dash-tile {
        grid-column: 1 / -1 !important;
        grid-row: auto !important;
      }
      .dash-grid.editing .dash-tile { cursor: default; }
      .resize-grip { display: none; }
    }

    .empty {
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 12px; padding: 60px 20px; color: var(--snm-text-muted);
      mat-icon { font-size: 48px; width: 48px; height: 48px; opacity: 0.4; }
    }
  `],
})
export class DashboardViewComponent implements OnInit {
  private readonly dashboards = inject(DashboardService);
  private readonly kpis = inject(KpiService);
  private readonly notify = inject(NotificationService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);

  readonly dashboard = signal<DashboardDetail | null>(null);
  readonly loading = signal(false);
  readonly editMode = signal(false);
  /** Working copy of items used during edit; commit on save. */
  readonly draftItems = signal<DashboardItem[]>([]);
  readonly dirty = signal(false);
  readonly loadError = signal<FormattedError | null>(null);
  /** Phase J.2 — true while the auto-decorate proposal is in flight. */
  readonly decorating = signal(false);

  readonly orderedItems = computed(() => {
    const src = this.editMode() ? this.draftItems() : (this.dashboard()?.items ?? []);
    // Stable order so trackBy keeps DOM nodes attached when only
    // grid coords change — the *visual* placement is driven by the
    // grid_x/y CSS variables, not array index.
    return [...src].sort((a, b) => (a.grid_y - b.grid_y) || (a.grid_x - b.grid_x));
  });

  // ---- Power BI–style drag + resize on a CSS Grid -----------------
  //
  // No external grid library: the layout is just CSS Grid with
  // ``grid-column / grid-row`` driven by per-tile CSS variables.
  // Drag/resize manipulate those variables directly via pointer
  // events; the ghost tile previews the snapped destination cell.

  /** Pixel height of one grid row. grid_h units multiply this.
   * 40px (was 80) gives 2× finer vertical control on drag/resize. */
  readonly rowHeight = 40;
  /** Number of columns — 24-col grid (refined from the original 12)
   * so horizontal drag/resize jumps in finer increments too. */
  private readonly cols = 24;

  @ViewChild('gridEl') private gridEl?: ElementRef<HTMLElement>;

  /** Tile id currently being dragged or resized — used to dim the
   * source tile while the ghost previews the new position. */
  readonly draggingItemId = signal<number | null>(null);
  /** Live ghost preview during drag/resize. Null when idle. */
  readonly ghost = signal<{ x: number; y: number; w: number; h: number } | null>(null);

  private interaction:
    | { kind: 'drag'; itemId: number; pointerId: number; startCellX: number; startCellY: number;
        offsetCellX: number; offsetCellY: number; w: number; h: number; cellW: number; cellH: number; }
    | { kind: 'resize'; itemId: number; pointerId: number; startW: number; startH: number;
        startCellX: number; startCellY: number; cellW: number; cellH: number; }
    | null = null;

  private gridGeometry(): { rect: DOMRect; cellW: number; cellH: number } | null {
    const el = this.gridEl?.nativeElement;
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    const styles = getComputedStyle(el);
    const gap = parseFloat(styles.gap) || 16;
    // Each column = (containerWidth - (cols-1)*gap) / cols
    const cellW = (rect.width - (this.cols - 1) * gap) / this.cols;
    const cellH = this.rowHeight + gap; // row + bottom gap; reverses on first row
    return { rect, cellW, cellH };
  }

  /** Convert a (clientX, clientY) into a (col, row) cell coordinate. */
  private pointToCell(x: number, y: number): { col: number; row: number } {
    const g = this.gridGeometry();
    if (!g) return { col: 0, row: 0 };
    const styles = getComputedStyle(this.gridEl!.nativeElement);
    const gap = parseFloat(styles.gap) || 16;
    const localX = x - g.rect.left;
    const localY = y - g.rect.top;
    const col = Math.max(0, Math.min(this.cols - 1, Math.floor(localX / (g.cellW + gap))));
    const row = Math.max(0, Math.floor(localY / (this.rowHeight + gap)));
    return { col, row };
  }

  onTilePointerDown(ev: PointerEvent, item: DashboardItem): void {
    if (!this.editMode()) return;
    // Don't start a drag from interactive children (refresh button,
    // menu, resize grip). Resize has its own handler.
    const target = ev.target as HTMLElement;
    if (target.closest('.resize-grip')) return;
    if (target.closest('button, a, mat-menu, [matMenuTriggerFor]')) return;
    const g = this.gridGeometry();
    if (!g) return;

    const styles = getComputedStyle(this.gridEl!.nativeElement);
    const gap = parseFloat(styles.gap) || 16;
    const tile = (ev.currentTarget as HTMLElement).getBoundingClientRect();
    const offsetCellX = Math.floor((ev.clientX - tile.left) / (g.cellW + gap));
    const offsetCellY = Math.floor((ev.clientY - tile.top) / (this.rowHeight + gap));

    this.interaction = {
      kind: 'drag',
      itemId: item.item_id,
      pointerId: ev.pointerId,
      startCellX: item.grid_x,
      startCellY: item.grid_y,
      offsetCellX,
      offsetCellY,
      w: item.grid_w,
      h: item.grid_h,
      cellW: g.cellW,
      cellH: g.cellH,
    };
    this.draggingItemId.set(item.item_id);
    this.ghost.set({ x: item.grid_x, y: item.grid_y, w: item.grid_w, h: item.grid_h });
    (ev.currentTarget as HTMLElement).setPointerCapture(ev.pointerId);
    ev.preventDefault();

    window.addEventListener('pointermove', this.onPointerMove);
    window.addEventListener('pointerup', this.onPointerUp);
    window.addEventListener('pointercancel', this.onPointerUp);
  }

  onResizePointerDown(ev: PointerEvent, item: DashboardItem): void {
    if (!this.editMode()) return;
    ev.stopPropagation(); // don't let the tile pointerdown also fire
    const g = this.gridGeometry();
    if (!g) return;
    this.interaction = {
      kind: 'resize',
      itemId: item.item_id,
      pointerId: ev.pointerId,
      startW: item.grid_w,
      startH: item.grid_h,
      startCellX: item.grid_x,
      startCellY: item.grid_y,
      cellW: g.cellW,
      cellH: g.cellH,
    };
    this.draggingItemId.set(item.item_id);
    this.ghost.set({ x: item.grid_x, y: item.grid_y, w: item.grid_w, h: item.grid_h });
    (ev.currentTarget as HTMLElement).setPointerCapture(ev.pointerId);
    ev.preventDefault();
    window.addEventListener('pointermove', this.onPointerMove);
    window.addEventListener('pointerup', this.onPointerUp);
    window.addEventListener('pointercancel', this.onPointerUp);
  }

  private readonly onPointerMove = (ev: PointerEvent): void => {
    const i = this.interaction;
    if (!i || ev.pointerId !== i.pointerId) return;

    if (i.kind === 'drag') {
      const cell = this.pointToCell(ev.clientX, ev.clientY);
      const x = Math.max(0, Math.min(this.cols - i.w, cell.col - i.offsetCellX));
      const y = Math.max(0, cell.row - i.offsetCellY);
      this.ghost.set({ x, y, w: i.w, h: i.h });
    } else {
      // Resize from the bottom-right corner.
      const tile = this.findTileEl(i.itemId);
      if (!tile) return;
      const tileRect = tile.getBoundingClientRect();
      const dx = ev.clientX - tileRect.left;
      const dy = ev.clientY - tileRect.top;
      const styles = getComputedStyle(this.gridEl!.nativeElement);
      const gap = parseFloat(styles.gap) || 16;
      const w = Math.max(1, Math.min(this.cols - i.startCellX,
        Math.round(dx / (i.cellW + gap)) || 1));
      const h = Math.max(1, Math.round(dy / (this.rowHeight + gap)) || 1);
      this.ghost.set({ x: i.startCellX, y: i.startCellY, w, h });
    }
  };

  private readonly onPointerUp = (ev: PointerEvent): void => {
    const i = this.interaction;
    if (!i || ev.pointerId !== i.pointerId) return;
    const ghost = this.ghost();
    this.cleanupInteraction();

    if (!ghost) return;
    // Commit the new coords to draft state. Collisions resolve with
    // a simple "shift the conflicting tile down" pass — keeps Power
    // BI's "no-overlap" invariant without a full pack algorithm.
    const target = i.itemId;
    const before = this.draftItems();
    const updated = before.map(it =>
      it.item_id === target
        ? { ...it, grid_x: ghost.x, grid_y: ghost.y, grid_w: ghost.w, grid_h: ghost.h }
        : it,
    );
    this.draftItems.set(this.resolveCollisions(updated, target));
    this.dirty.set(true);
  };

  private cleanupInteraction(): void {
    this.interaction = null;
    this.draggingItemId.set(null);
    this.ghost.set(null);
    window.removeEventListener('pointermove', this.onPointerMove);
    window.removeEventListener('pointerup', this.onPointerUp);
    window.removeEventListener('pointercancel', this.onPointerUp);
  }

  private findTileEl(itemId: number): HTMLElement | null {
    const grid = this.gridEl?.nativeElement;
    if (!grid) return null;
    // Find the tile whose --gx/--gy/--gw/--gh match the item's saved
    // coords (we don't render id attributes).
    const item = this.draftItems().find(it => it.item_id === itemId);
    if (!item) return null;
    const tiles = Array.from(grid.querySelectorAll<HTMLElement>('.dash-tile'));
    return tiles.find(t => {
      const s = t.style;
      return parseInt(s.getPropertyValue('--gx') || '0', 10) === item.grid_x
          && parseInt(s.getPropertyValue('--gy') || '0', 10) === item.grid_y;
    }) ?? null;
  }

  /** Push any tile that overlaps with ``movedId`` down one row at a
   * time until there's no collision. Stable: tiles only move down,
   * never sideways, so the user's spatial intent stays intact. */
  private resolveCollisions(items: DashboardItem[], movedId: number): DashboardItem[] {
    const moved = items.find(it => it.item_id === movedId);
    if (!moved) return items;
    let result = items.slice();
    let madeProgress = true;
    let safety = 50; // hard cap so a pathological layout can't loop forever
    while (madeProgress && safety-- > 0) {
      madeProgress = false;
      for (let i = 0; i < result.length; i++) {
        const a = result[i];
        if (a.item_id === movedId) continue;
        if (this.overlaps(a, moved)) {
          result[i] = { ...a, grid_y: moved.grid_y + moved.grid_h };
          madeProgress = true;
        }
      }
      // After bumping siblings, they may now collide with each
      // other; loop until the layout is stable.
    }
    return result;
  }

  /** One-click tight pack: every tile floats upward into the lowest
   * empty row that can hold its (w, h) without overlapping any tile
   * already placed there. Iterates in row-major order so the visual
   * top-left → bottom-right reading flow is preserved. */
  compactLayout(): void {
    const items = [...this.draftItems()].sort(
      (a, b) => (a.grid_y - b.grid_y) || (a.grid_x - b.grid_x),
    );
    const placed: DashboardItem[] = [];
    for (const it of items) {
      // Find the smallest grid_y where this tile fits without
      // overlapping anything already placed.
      let y = 0;
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const candidate = { ...it, grid_y: y };
        const collides = placed.some(p => this.overlaps(p, candidate));
        if (!collides) {
          placed.push(candidate);
          break;
        }
        y++;
        // Hard cap so a malformed layout can't loop forever.
        if (y > 999) {
          placed.push(candidate);
          break;
        }
      }
    }
    this.draftItems.set(placed);
    this.dirty.set(true);
  }

  private overlaps(a: DashboardItem, b: DashboardItem): boolean {
    return !(
      a.grid_x + a.grid_w <= b.grid_x ||
      b.grid_x + b.grid_w <= a.grid_x ||
      a.grid_y + a.grid_h <= b.grid_y ||
      b.grid_y + b.grid_h <= a.grid_y
    );
  }

  /** Show "Manage Assignees" only to SuperAdmin or the dashboard owner.
   * The backend enforces this anyway; hiding the button is just UX. */
  readonly canManageAssignees = computed(() => {
    const u = this.auth.getCurrentUser();
    const d = this.dashboard();
    if (!u || !d) return false;
    if (u.isSuperAdmin) return true;
    return d.owner_user_id === u.userId;
  });

  ngOnInit(): void {
    const idParam = this.route.snapshot.paramMap.get('id');
    if (!idParam) return;
    if (this.route.snapshot.data['mode'] === 'edit') {
      this.editMode.set(true);
    }
    this.load(parseInt(idParam, 10));
  }

  private load(id: number, keepDraft = false): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.dashboards.get(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: d => {
          this.dashboard.set(d);
          if (!keepDraft) {
            this.draftItems.set([...d.items]);
            this.dirty.set(false);
          }
          this.loading.set(false);
        },
        error: err => {
          this.loading.set(false);
          this.loadError.set(formatHttpError(err, 'Failed to load dashboard'));
        },
      });
  }

  enterEdit(): void {
    this.editMode.set(true);
    this.draftItems.set([...(this.dashboard()?.items ?? [])]);
    this.dirty.set(false);
  }

  cancelEdit(): void {
    this.editMode.set(false);
    this.draftItems.set([...(this.dashboard()?.items ?? [])]);
    this.dirty.set(false);
  }

  saveLayout(): void {
    const d = this.dashboard();
    if (!d) return;
    this.loading.set(true);
    // Position is recomputed from grid_y so the legacy field stays
    // in sync — a row-major top-to-bottom ordering matches "what the
    // user sees" if they ever switch back to a flow layout.
    const sorted = [...this.draftItems()].sort(
      (a, b) => (a.grid_y - b.grid_y) || (a.grid_x - b.grid_x),
    );
    const payload = {
      items: sorted.map((it, i) => ({
        item_id: it.item_id,
        position: i,
        size_class: it.size_class,
        grid_x: it.grid_x,
        grid_y: it.grid_y,
        grid_w: it.grid_w,
        grid_h: it.grid_h,
        // Phase J.2 — persist AI Polish overrides in the same PUT.
        // The backend treats null as "leave unchanged" and an empty
        // string as "clear", so we send what we have on the draft.
        title_override: it.title_override,
        icon: it.icon ?? null,
        animation_in: it.animation_in ?? null,
        animation_out: it.animation_out ?? null,
        x_label: it.x_label ?? null,
        y_label: it.y_label ?? null,
        extra_filters: it.extra_filters ?? [],
      })),
    };
    this.dashboards.saveLayout(d.dashboard_id, payload)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: updated => {
          this.dashboard.set(updated);
          this.draftItems.set([...updated.items]);
          this.dirty.set(false);
          this.loading.set(false);
          this.notify.success('Layout saved.');
        },
        error: err => {
          this.loading.set(false);
          this.notify.error(err?.error?.detail?.message ?? err?.error?.detail ?? 'Save failed');
        },
      });
  }

  reloadAll(): void {
    const d = this.dashboard();
    if (d) this.load(d.dashboard_id);
  }

  /** Phase J.2 — apply an AI-proposed layout to the working draft.
   * The proposal is *advisory* (just sizes + grid coords + an optional
   * shorter title); the user still needs to click Save to persist. */
  autoDecorate(): void {
    const d = this.dashboard();
    if (!d || this.decorating()) return;
    this.decorating.set(true);
    this.dashboards.autoDecorate(d.dashboard_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.decorating.set(false);
          if (!res.items.length) {
            this.notify.info('No layout changes proposed.');
            return;
          }
          // Apply ONLY the polish fields from the proposal. AI Polish
          // never changes layout — the user's manual arrangement
          // (drag/drop + Compact-up) is preserved exactly. The
          // backend pins grid_x/y/w/h + size_class server-side, but
          // we also ignore them here so a future API change can't
          // accidentally re-introduce layout drift.
          const byId = new Map(res.items.map(p => [p.item_id, p]));
          const next: DashboardItem[] = this.draftItems().map(it => {
            const p = byId.get(it.item_id);
            if (!p) return it;
            return {
              ...it,
              title_override: p.title_override ?? it.title_override,
              icon: p.icon ?? it.icon ?? null,
              animation_in: p.animation_in ?? it.animation_in ?? null,
              animation_out: p.animation_out ?? it.animation_out ?? null,
              x_label: p.x_label ?? it.x_label ?? null,
              y_label: p.y_label ?? it.y_label ?? null,
              extra_filters: p.extra_filters ?? it.extra_filters ?? [],
            };
          });
          this.draftItems.set(next);
          this.dirty.set(true);
          if (res.used_fallback) {
            this.notify.info(
              res.error === 'llm_disabled'
                ? 'No AI provider configured — your layout stays as-is. Set up a provider in Settings to get polish suggestions.'
                : 'AI was unavailable — your layout stays as-is.',
            );
          } else {
            // Count items that actually got new visual polish — the
            // notification should reflect what changed (icons, animations,
            // axis labels, filters), not just "N cards" since layout
            // never changes here.
            const polished = res.items.filter(p =>
              p.icon || p.animation_in || p.animation_out
              || p.x_label || p.y_label
              || (p.extra_filters && p.extra_filters.length),
            ).length;
            if (polished === 0) {
              this.notify.info('AI had no polish suggestions for this dashboard.');
            } else {
              this.notify.success(
                `AI polished ${polished} card${polished === 1 ? '' : 's'} (icons, animations, filters). Click Save to keep it.`,
              );
            }
          }
        },
        error: err => {
          this.decorating.set(false);
          this.notify.error(
            err?.error?.detail?.message ?? err?.error?.detail ?? 'Auto-decorate failed',
          );
        },
      });
  }

  openAssigneesDialog(): void {
    const d = this.dashboard();
    if (!d) return;
    this.dialog.open(ManageAssigneesDialogComponent, {
      width: '560px',
      maxWidth: '92vw',
      data: <ManageAssigneesDialogData>{
        dashboardId: d.dashboard_id,
        dashboardName: d.name,
      },
    });
    // Dialog manages its own state; no need to refresh the dashboard
    // metadata after close — the assignment list lives in the dialog
    // and on the backend.
  }

  openAddKpi(): void {
    const d = this.dashboard();
    if (!d) return;
    const ref = this.dialog.open(AddKpiDialogComponent, { width: '520px' });
    ref.afterClosed().pipe(takeUntilDestroyed(this.destroyRef)).subscribe((kpi: KpiSummary | undefined) => {
      if (!kpi) return;
      this.dashboards.addItem(d.dashboard_id, { kpi_id: kpi.kpi_id, size_class: 'md' })
        .subscribe({
          next: item => {
            this.draftItems.set([...this.draftItems(), item]);
            // Backend already persisted; pull a fresh detail in-place.
            this.load(d.dashboard_id, /*keepDraft=*/false);
            this.notify.success(`Added "${kpi.name}".`);
          },
          error: err => this.notify.error(err?.error?.detail?.message ?? 'Add failed'),
        });
    });
  }

  confirmRemove(it: DashboardItem): void {
    const d = this.dashboard();
    if (!d) return;
    const ref = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: 'Remove card?',
        message: `"${it.title_override || it.kpi_name}" will be removed from this dashboard. The KPI itself stays.`,
        confirmText: 'Remove',
      },
    });
    ref.afterClosed().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(ok => {
      if (!ok) return;
      this.dashboards.removeItem(d.dashboard_id, it.item_id).subscribe({
        next: () => { this.load(d.dashboard_id); this.notify.success('Card removed.'); },
        error: err => this.notify.error(err?.error?.detail?.message ?? 'Remove failed'),
      });
    });
  }

  back(): void {
    this.router.navigate(['/kpi-studio/dashboards']);
  }

  trackItem = (_: number, it: DashboardItem) => it.item_id;
}
