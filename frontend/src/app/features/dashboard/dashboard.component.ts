import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  HostListener,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { AuthService } from '../../core/auth/auth.service';
import { DashboardService } from '../kpi-studio/services/dashboard.service';
import {
  CardSize,
  DashboardItem,
  TimePeriodSelection,
} from '../kpi-studio/models/schema.types';
import { KpiCardComponent } from '../kpi-studio/components/kpi-card/kpi-card.component';
import { PeriodSelectorComponent } from '../kpi-studio/components/period-selector/period-selector.component';
import { ChatPanelComponent } from '../kpi-studio/components/chat-panel/chat-panel.component';

/** Order in which sizes are compared (small → wide). The unified view
 * always picks the largest size when the same KPI appears on multiple
 * dashboards with different sizes — never shrinks a card. */
const SIZE_RANK: Record<CardSize, number> = {
  sm: 1, md: 2, lg: 3, wide: 4,
};

@Component({
  selector: 'app-dashboard',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, RouterLink,
    MatButtonModule, MatIconModule, MatChipsModule, MatProgressBarModule,
    MatTooltipModule,
    KpiCardComponent, PeriodSelectorComponent, ChatPanelComponent,
  ],
  template: `
    <div class="dashboard-page">
      <!-- Welcome strip -->
      <header class="welcome-strip">
        <div class="welcome-text">
          <mat-icon class="welcome-icon">waving_hand</mat-icon>
          <div>
            <h2>Welcome, {{ user()?.userName }}</h2>
            <p class="meta">
              {{ user()?.companyName }}
              <span class="dot">·</span>
              {{ user()?.roleName }}
              <mat-chip *ngIf="user()?.isSuperAdmin" class="super-chip" disabled>
                Super Admin
              </mat-chip>
            </p>
          </div>
        </div>
        <button mat-stroked-button color="primary"
                *ngIf="user()?.isSuperAdmin"
                (click)="openKpiStudio()">
          <mat-icon>tune</mat-icon>
          Manage in KPI Studio
        </button>
      </header>

      <!-- Period filter — applies to every card on this page -->
      <app-period-selector
        [value]="period().period"
        (periodChange)="onPeriodChange($event)" />

      <mat-progress-bar *ngIf="loading()" mode="indeterminate"></mat-progress-bar>

      <div *ngIf="loadError()" class="error-banner">
        <mat-icon>error_outline</mat-icon>
        <span>{{ loadError() }}</span>
        <button mat-stroked-button (click)="load()">Retry</button>
      </div>

      <!-- Unified, deduplicated KPI grid. Native 12-column CSS Grid —
           each tile claims its grid_x/y/w/h slot. No transforms, no
           stacking-context surprises; the welcome strip's clean glass
           look extends to every tile. Drag/resize live in the
           dashboard editor (Step 2 onwards). -->
      <section class="grid-section" *ngIf="!loading() && !loadError()">
        <div *ngIf="mergedItems().length; else emptyTpl"
             class="dash-grid"
             [style.--row-h.px]="rowHeight">
          <div *ngFor="let it of mergedItems(); let i = index; trackBy: trackItem"
               class="dash-tile"
               [style.--gx]="it.grid_x"
               [style.--gy]="it.grid_y"
               [style.--gw]="it.grid_w"
               [style.--gh]="it.grid_h"
               [style.animation-delay.ms]="i * 60">
            <app-kpi-card [item]="it" [period]="period()"
                          [showResize]="false" />
          </div>
        </div>

        <ng-template #emptyTpl>
          <div class="empty">
            <mat-icon>inbox</mat-icon>
            <h3>No dashboards yet</h3>
            <p *ngIf="user()?.isSuperAdmin">
              Create your first one in
              <a (click)="openKpiStudio()" class="link">KPI Studio</a>.
            </p>
            <p *ngIf="!user()?.isSuperAdmin">
              Ask your administrator to assign a dashboard to your role or account.
            </p>
          </div>
        </ng-template>
      </section>

      <!-- Smart Analysis: floating button + slide-out panel.
           SuperAdmin only for now (matches the menu visibility rule).
           Compact mode hides the sessions sidebar so the panel fits
           comfortably as an overlay. -->
      <ng-container *ngIf="user()?.isSuperAdmin">
        <button mat-fab
                class="chat-fab"
                color="primary"
                (click)="toggleChat()"
                [matTooltip]="chatOpen() ? 'Close Smart Analysis' : 'Open Smart Analysis'">
          <mat-icon>{{ chatOpen() ? 'close' : 'smart_toy' }}</mat-icon>
        </button>
        <div *ngIf="chatOpen()"
             class="chat-overlay"
             (click)="toggleChat()"></div>
        <aside class="chat-drawer"
               [class.open]="chatOpen()"
               [class.resizing]="chatResizing()"
               [style.width.px]="chatWidth()">
          <!-- Drag handle on the left edge — pull leftwards to widen.
               Width is clamped to [360 px, 50 vw] on large screens and
               to the full viewport on small ones, persisted to
               localStorage so the user's preference survives reloads. -->
          <div class="resize-handle"
               role="separator"
               aria-orientation="vertical"
               aria-label="Resize Smart Analysis"
               (mousedown)="onResizeStart($event)"
               (touchstart)="onResizeStart($event)"
               (dblclick)="resetChatWidth()"
               matTooltip="Drag to resize · double-click to reset"></div>
          <header class="drawer-head">
            <mat-icon class="head-icon">smart_toy</mat-icon>
            <strong>Smart Analysis</strong>
            <span class="spacer"></span>
            <a mat-icon-button
               [routerLink]="['/kpi-studio/chat']"
               matTooltip="Open full page">
              <mat-icon>open_in_full</mat-icon>
            </a>
            <button mat-icon-button (click)="toggleChat()" matTooltip="Close">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <div class="drawer-body">
            <!-- chatOpen() guard avoids fetching sessions until the
                 panel is actually visible. -->
            <app-chat-panel *ngIf="chatOpen()" [compact]="true"></app-chat-panel>
          </div>
        </aside>
      </ng-container>
    </div>
  `,
  styles: [`
    .dashboard-page { padding: 24px; display: flex; flex-direction: column; gap: 16px; }

    .welcome-strip {
      display: flex; justify-content: space-between; align-items: center;
      flex-wrap: wrap; gap: 12px;
      padding: 14px 18px;
      background: var(--snm-bg-card, #fff);
      border: 1px solid var(--snm-border-divider, #e0e0e0);
      border-radius: 8px;
    }
    .welcome-text { display: flex; align-items: center; gap: 12px; }
    .welcome-text h2 {
      margin: 0; font-size: 1.2rem; color: var(--snm-text-primary);
      font-weight: 600;
    }
    .welcome-text .meta {
      margin: 2px 0 0; color: var(--snm-text-muted); font-size: 0.85rem;
      display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
    }
    .dot { opacity: 0.5; }
    .welcome-icon {
      font-size: 32px; width: 32px; height: 32px;
      color: var(--snm-accent, #4a90e2);
    }
    .super-chip {
      font-size: 0.7rem;
      background: rgba(255, 167, 38, 0.15);
      color: #e65100;
    }

    .grid-section { display: flex; flex-direction: column; gap: 12px; }

    /* Native 24-column CSS Grid (refined from 12 so drag/resize
       jumps in finer increments). Each tile uses CSS variables from
       its DashboardItem to claim a (x, y, w, h) rectangle. Mobile
       collapses to a single column via the media query below. */
    .dash-grid {
      display: grid;
      grid-template-columns: repeat(24, 1fr);
      grid-auto-rows: var(--row-h, 40px);
      gap: 12px;
      width: 100%;
    }
    .dash-tile {
      grid-column: calc(var(--gx) + 1) / span var(--gw);
      grid-row:    calc(var(--gy) + 1) / span var(--gh);
      min-width: 0;
      display: flex;
      /* Staggered mount — each tile fades + slides up on first
         render. The inline animation-delay on each tile multiplies
         this by 60ms × index for a cascading reveal. */
      animation: dash-tile-enter 420ms cubic-bezier(0.2, 0, 0, 1) both;
    }
    @keyframes dash-tile-enter {
      from { opacity: 0; transform: translateY(10px) scale(0.985); }
      to   { opacity: 1; transform: none; }
    }
    .dash-tile > app-kpi-card { flex: 1; min-width: 0; }

    /* Mobile — collapse to one column, auto row heights so each
       card sizes to its chart content instead of being clipped. */
    @media (max-width: 768px) {
      .dash-grid {
        grid-template-columns: 1fr;
        grid-auto-rows: minmax(280px, auto);
      }
      .dash-tile {
        grid-column: 1 / -1 !important;
        grid-row: auto !important;
      }
    }

    .empty {
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 4px; padding: 60px 20px;
      color: var(--snm-text-muted);
      animation: empty-fade-in 600ms cubic-bezier(0.2, 0, 0, 1) both;
      mat-icon {
        font-size: 56px; width: 56px; height: 56px; opacity: 0.35;
        /* Soft float — barely visible, gives the empty state a tiny
           heartbeat instead of looking like a broken page. */
        animation: empty-float 4.2s ease-in-out infinite;
      }
      h3 { margin: 4px 0 0; color: var(--snm-text-secondary); }
      p { margin: 0; }
      .link { color: var(--snm-accent); cursor: pointer; text-decoration: underline; }
    }
    @keyframes empty-fade-in {
      from { opacity: 0; transform: translateY(8px); }
      to   { opacity: 1; transform: none; }
    }
    @keyframes empty-float {
      0%, 100% { transform: translateY(0); }
      50%      { transform: translateY(-4px); }
    }

    .error-banner {
      display: flex; gap: 8px; padding: 12px 16px;
      background: rgba(229, 57, 53, 0.08);
      border: 1px solid var(--snm-error, #e53935);
      border-radius: 6px; align-items: center;
      mat-icon { color: var(--snm-error, #e53935); }
      span { flex: 1; color: var(--snm-text-primary); font-size: 0.9rem; }
    }

    /* Smart Analysis chat — floating action button + slide-out drawer.
       Drawer is fixed-position so it doesn't affect the dashboard
       layout; overlay catches outside-clicks to close. */
    .chat-fab {
      position: fixed;
      bottom: 24px; right: 24px;
      z-index: 998;
    }
    .chat-overlay {
      position: fixed; inset: 0;
      background: rgba(0, 0, 0, 0.25);
      z-index: 999;
    }
    /* The drawer is anchored to the right edge of the viewport. Its
       width is bound inline (driven by the resize signal) so the panel
       can be dragged wider; opening / closing slides it via translateX
       so the reveal animates as a smooth left-ward expansion (the right
       edge stays pinned, the left edge slides in from the right edge
       into its final position). Width is independent of the open/close
       animation so the resize drag never fights the slide.

       Background uses --snm-glass-bg-solid (75-85% alpha) PLUS a
       backdrop-filter blur — same frosted-glass pattern the sidenav
       uses — so the toolbar text behind doesn't bleed through. The
       earlier --snm-bg-card was 45-60% alpha and let the company
       switcher / theme toggle visually mix with the drawer header.

       max-width is the hard ceiling: 50vw on >768px viewports, 100vw
       on phones. CSS belt-and-braces with the JS clamp in
       clampChatWidth() — if anything bypasses the signal, the drawer
       still can't grow past these caps. */
    .chat-drawer {
      position: fixed;
      top: 0; right: 0; bottom: 0;
      max-width: 50vw;
      background: var(--snm-glass-bg-solid, #fff);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border-left: 1px solid var(--snm-glass-border, var(--snm-border-divider, #e0e0e0));
      box-shadow: -8px 0 24px var(--snm-glass-shadow-heavy, rgba(0, 0, 0, 0.18));
      z-index: 1000;
      display: flex;
      flex-direction: column;
      transform: translateX(100%);
      transition: transform 320ms cubic-bezier(0.32, 0.72, 0.24, 1);
      will-change: transform;
    }
    .chat-drawer.open { transform: translateX(0); }
    /* Disable the slide animation while the user is dragging the resize
       handle so width changes don't get smoothed away. */
    .chat-drawer.resizing { transition: none; }

    /* Phones and very narrow tablets — let the drawer fill the
       viewport so the chat is usable. Mirrors clampChatWidth's small
       device branch. */
    @media (max-width: 768px) {
      .chat-drawer { max-width: 100vw; }
    }

    .resize-handle {
      position: absolute;
      top: 0; bottom: 0; left: -3px;
      width: 6px;
      cursor: ew-resize;
      z-index: 2;
      background: transparent;
      transition: background 120ms ease;
    }
    .resize-handle:hover,
    .chat-drawer.resizing .resize-handle {
      background: var(--snm-accent-subtle);
    }
    .drawer-head {
      display: flex; align-items: center; gap: 8px;
      padding: 10px 14px;
      border-bottom: 1px solid var(--snm-border-divider, #e0e0e0);
      .head-icon {
        color: var(--snm-accent, #4a90e2);
      }
      .spacer { flex: 1; }
      strong { color: var(--snm-text-primary); }
    }
    /* Flex column so the chat-panel host (flex:1 column) sizes
       correctly. */
    .drawer-body {
      flex: 1 1 0; min-height: 0;
      display: flex; flex-direction: column;
    }
  `],
})
export class DashboardComponent implements OnInit {
  private readonly authService = inject(AuthService);
  private readonly dashboardsApi = inject(DashboardService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(false);
  readonly loadError = signal<string | null>(null);
  readonly mergedItems = signal<DashboardItem[]>([]);
  readonly dashboardCount = signal(0);
  readonly period = signal<TimePeriodSelection>({ period: null });
  /** Smart Analysis chat drawer toggle. */
  readonly chatOpen = signal(false);
  /** Active drawer width in px — bound to the aside's inline style.
   *  Initialized from localStorage so the user's preference survives
   *  reloads. Clamped on read in case the persisted value was saved on
   *  a wider screen than the current one. */
  readonly chatWidth = signal<number>(this.readPersistedChatWidth());
  /** Breakpoint below which the drawer fills the viewport (phone-sized
   *  devices). Above it, the cap drops back to 50 vw. */
  private readonly CHAT_SMALL_DEVICE_PX = 768;
  /** True only while the user is actively dragging the resize handle —
   *  used to disable transition animations on the drawer for that frame. */
  readonly chatResizing = signal(false);
  private readonly CHAT_WIDTH_MIN = 360;
  private readonly CHAT_WIDTH_DEFAULT = 560;
  private readonly CHAT_WIDTH_KEY = 'snm-chat-drawer-width';

  readonly user = computed(() => this.authService.getCurrentUser());

  toggleChat(): void {
    this.chatOpen.update(v => !v);
  }

  // ---- Drawer resize -----------------------------------------------------

  private readPersistedChatWidth(): number {
    try {
      const raw = localStorage.getItem('snm-chat-drawer-width');
      const n = raw ? Number(raw) : NaN;
      if (Number.isFinite(n) && n > 0) {
        return this.clampChatWidth(n);
      }
    } catch { /* localStorage may be blocked — fall through */ }
    return 560;
  }

  /**
   * Responsive clamp:
   *   - Small device (viewport <= 768 px) → drawer can stretch to the
   *     full viewport (100 %), and the floor drops to whatever the
   *     viewport allows so phones don't end up with a 360 px panel
   *     hanging off-screen.
   *   - Larger device → drawer caps at 50 vw, floor stays at 360 px.
   * Always returns an integer so the inline-style binding is stable.
   */
  private clampChatWidth(px: number): number {
    const vw = window.innerWidth;
    const isSmall = vw <= this.CHAT_SMALL_DEVICE_PX;
    const max = isSmall ? vw : Math.max(this.CHAT_WIDTH_MIN, Math.floor(vw * 0.5));
    const min = isSmall ? Math.min(vw, this.CHAT_WIDTH_MIN) : this.CHAT_WIDTH_MIN;
    return Math.min(Math.max(min, Math.round(px)), max);
  }

  /**
   * Begin a resize drag. We bind document-level listeners so the user
   * can pull the cursor outside the handle without losing the drag —
   * a standard "drag tracker" pattern. Uses pointer-screen coords
   * (clientX) and the drawer's right-anchored geometry: width is
   * ``window.innerWidth - clientX``.
   */
  onResizeStart(event: MouseEvent | TouchEvent): void {
    event.preventDefault();
    this.chatResizing.set(true);

    const move = (e: MouseEvent | TouchEvent) => {
      const clientX = ('touches' in e)
        ? (e.touches[0]?.clientX ?? 0)
        : (e as MouseEvent).clientX;
      const next = this.clampChatWidth(window.innerWidth - clientX);
      this.chatWidth.set(next);
    };

    const end = () => {
      this.chatResizing.set(false);
      document.removeEventListener('mousemove', move);
      document.removeEventListener('mouseup', end);
      document.removeEventListener('touchmove', move);
      document.removeEventListener('touchend', end);
      try { localStorage.setItem(this.CHAT_WIDTH_KEY, String(this.chatWidth())); }
      catch { /* persistence is best-effort */ }
    };

    document.addEventListener('mousemove', move, { passive: true });
    document.addEventListener('mouseup', end);
    document.addEventListener('touchmove', move, { passive: true });
    document.addEventListener('touchend', end);
  }

  /** Double-click handle → reset to the default width. */
  resetChatWidth(): void {
    this.chatWidth.set(this.clampChatWidth(this.CHAT_WIDTH_DEFAULT));
    try { localStorage.setItem(this.CHAT_WIDTH_KEY, String(this.chatWidth())); }
    catch { /* persistence is best-effort */ }
  }

  /**
   * Re-clamp on viewport changes — handles device rotation, window
   * resize, and the small-vs-large-device threshold flip cleanly. We
   * don't persist the new value back to localStorage because the user
   * didn't choose this width; it's just an enforced upper bound.
   */
  @HostListener('window:resize')
  onWindowResize(): void {
    this.chatWidth.update(w => this.clampChatWidth(w));
  }

  ngOnInit(): void {
    this.load();
  }

  /**
   * Pulls every dashboard the user has access to, fetches each detail
   * in parallel, then merges the items into a single list keyed by
   * ``kpi_id``. Conflict resolution per the design: largest size wins,
   * ``title_override`` is dropped (canonical KPI name only).
   */
  load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.dashboardsApi.list()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: list => {
          if (!list.items.length) {
            this.mergedItems.set([]);
            this.dashboardCount.set(0);
            this.loading.set(false);
            return;
          }
          this.dashboardCount.set(list.items.length);

          // Fetch each dashboard's detail in parallel; tolerate per-dashboard
          // failures so one broken board doesn't kill the whole page.
          const detailCalls = list.items.map(d =>
            this.dashboardsApi.get(d.dashboard_id).pipe(
              catchError(err => {
                // eslint-disable-next-line no-console
                console.warn('[dashboard] could not load details for', d.dashboard_id, err);
                return of(null);
              }),
            ),
          );
          forkJoin(detailCalls)
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
              next: details => {
                this.mergedItems.set(this.mergeItems(details));
                this.loading.set(false);
              },
              error: err => {
                this.loading.set(false);
                this.loadError.set(`Could not load dashboard details (status ${err?.status ?? 0}).`);
                // eslint-disable-next-line no-console
                console.error('[dashboard] forkJoin failed', err);
              },
            });
        },
        error: err => {
          this.loading.set(false);
          const status = err?.status ?? 0;
          this.loadError.set(
            status === 403
              ? 'Your role does not have permission to view dashboards.'
              : `Could not load dashboards (status ${status}).`,
          );
          // eslint-disable-next-line no-console
          console.error('[dashboard] load failed', err);
        },
      });
  }

  /**
   * Walks every dashboard's items, picks the unique-by-kpi_id set, and
   * for each duplicate keeps the largest size. ``title_override`` is
   * intentionally dropped — the canonical KPI name renders, regardless
   * of any per-dashboard rename.
   *
   * Order: respect the source dashboard's ``position``. When a KPI is
   * on multiple dashboards, the *first dashboard it appears in* (in
   * the order returned by ``/dashboards``) gives it its slot. Earlier
   * versions sorted alphabetically — that lost the user's deliberate
   * arrangement and broke "drag to reorder" flows on the editor.
   */
  private mergeItems(details: Array<{ items: DashboardItem[] } | null>): DashboardItem[] {
    interface MergedEntry {
      item: DashboardItem;
      sourceDashIdx: number;
      sourcePosition: number;
    }
    const byKpi = new Map<number, MergedEntry>();

    details.forEach((d, dashIdx) => {
      if (!d) return;
      for (const it of d.items) {
        const existing = byKpi.get(it.kpi_id);
        if (!existing) {
          byKpi.set(it.kpi_id, {
            item: { ...it, title_override: null },
            sourceDashIdx: dashIdx,
            sourcePosition: it.position,
          });
          continue;
        }
        // Conflict resolution: keep the largest size; ordering is
        // anchored to the first sighting (no churn when later
        // dashboards add the same KPI).
        if (SIZE_RANK[it.size_class] > SIZE_RANK[existing.item.size_class]) {
          existing.item = { ...existing.item, size_class: it.size_class };
        }
      }
    });

    return Array.from(byKpi.values())
      .sort((a, b) =>
        (a.sourceDashIdx - b.sourceDashIdx)
        || (a.sourcePosition - b.sourcePosition)
        || (a.item.kpi_id - b.item.kpi_id),
      )
      .map(e => e.item);
  }

  onPeriodChange(sel: TimePeriodSelection): void {
    this.period.set(sel);
    // Cards have an ``effect()`` that watches the period input, so they
    // re-run /kpis/{id}/run on their own when the binding changes — no
    // explicit reload here.
  }

  // ---- Power BI grid (read-only on /dashboard) ----------------------
  /** Grid row height in pixels. Each grid_h unit = this many px;
   * matches the value the dashboard editor uses so layouts saved
   * there render at the same vertical scale here. */
  readonly rowHeight = 40;

  openKpiStudio(): void {
    this.router.navigate(['/kpi-studio/dashboards']);
  }

  trackItem = (_: number, it: DashboardItem) => it.kpi_id;
}
