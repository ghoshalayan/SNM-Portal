import { Component, OnInit, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';
import * as dagre from 'dagre';

export interface OrgUser {
  userId: number;
  userName: string;
  userCode?: string;
  userEmail?: string;
  reportTo?: number | null;
  roleName?: string;
  // Layout (computed)
  x?: number;
  y?: number;
}

export interface OrgEdge {
  sourceId: number;
  targetId: number;
  path: string;
}

@Component({
  selector: 'app-org-tree',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
    MatTooltipModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './org-tree.component.html',
  styleUrl: './org-tree.component.scss',
})
export class OrgTreeComponent implements OnInit {
  allUsers: OrgUser[] = [];
  assignedUsers: OrgUser[] = [];
  unassignedUsers: OrgUser[] = [];
  edges: OrgEdge[] = [];
  loading = true;

  // Canvas transform state
  scale = 1;
  translateX = 0;
  translateY = 0;

  // Drag state
  draggingUserId: number | null = null;
  dropTargetUserId: number | null = null;

  // Pan state
  isPanning = false;
  private panStartX = 0;
  private panStartY = 0;
  private panStartTX = 0;
  private panStartTY = 0;

  // Layout constants
  readonly NODE_W = 220;
  readonly NODE_H = 84;
  canvasW = 1400;
  canvasH = 900;

  constructor(
    private api: ApiService,
    private notify: NotificationService,
  ) {}

  ngOnInit(): void {
    this.loadOrgTree();
  }

  // ── Data ────────────────────────────────────────────────────────────────

  loadOrgTree(): void {
    this.loading = true;
    this.api.get<OrgUser[]>('/org-tree').subscribe({
      next: (users) => {
        this.allUsers = users;
        this.computeLayout();
        this.loading = false;
      },
      error: () => {
        this.notify.error('Failed to load organization tree');
        this.loading = false;
      },
    });
  }

  // ── Layout ──────────────────────────────────────────────────────────────

  computeLayout(): void {
    // Build sets for classification
    const reportedToByOther = new Set<number>();
    for (const u of this.allUsers) {
      if (u.reportTo && u.reportTo !== u.userId) {
        reportedToByOther.add(u.reportTo);
      }
    }

    // Assigned = has reportTo (including self-ref root) OR someone reports to them
    this.assignedUsers = this.allUsers.filter(
      u => u.reportTo != null || reportedToByOther.has(u.userId),
    );
    this.unassignedUsers = this.allUsers.filter(
      u => u.reportTo == null && !reportedToByOther.has(u.userId),
    );

    if (this.assignedUsers.length === 0) {
      this.edges = [];
      return;
    }

    const g = new dagre.graphlib.Graph();
    g.setGraph({
      rankdir: 'TB',
      nodesep: 80,
      ranksep: 120,
      marginx: 60,
      marginy: 60,
    });
    g.setDefaultEdgeLabel(() => ({}));

    for (const u of this.assignedUsers) {
      g.setNode(String(u.userId), { width: this.NODE_W, height: this.NODE_H });
    }

    for (const u of this.assignedUsers) {
      if (u.reportTo && u.reportTo !== u.userId) {
        const parentInTree = this.assignedUsers.find(p => p.userId === u.reportTo);
        if (parentInTree) {
          g.setEdge(String(u.reportTo), String(u.userId));
        }
      }
    }

    dagre.layout(g);

    for (const u of this.assignedUsers) {
      const node = g.node(String(u.userId));
      if (node) {
        u.x = node.x - this.NODE_W / 2;
        u.y = node.y - this.NODE_H / 2;
      }
    }

    // Build edge paths (bezier curves)
    this.edges = [];
    for (const u of this.assignedUsers) {
      if (u.reportTo && u.reportTo !== u.userId) {
        const parent = this.assignedUsers.find(p => p.userId === u.reportTo);
        if (parent && parent.x != null && u.x != null) {
          const x1 = parent.x + this.NODE_W / 2;
          const y1 = parent.y! + this.NODE_H;
          const x2 = u.x + this.NODE_W / 2;
          const y2 = u.y!;
          const midY = (y1 + y2) / 2;
          this.edges.push({
            sourceId: parent.userId,
            targetId: u.userId,
            path: `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`,
          });
        }
      }
    }

    // Size the canvas to fit
    const info = g.graph();
    this.canvasW = Math.max(1400, (info.width || 800) + 200);
    this.canvasH = Math.max(900, (info.height || 600) + 200);
  }

  // ── Drag & Drop ─────────────────────────────────────────────────────────

  onDragStart(ev: DragEvent, userId: number): void {
    this.draggingUserId = userId;
    ev.dataTransfer?.setData('text/plain', String(userId));
    if (ev.dataTransfer) ev.dataTransfer.effectAllowed = 'move';
  }

  onDragOverNode(ev: DragEvent, targetId: number): void {
    ev.preventDefault();
    ev.stopPropagation();
    if (this.draggingUserId && this.draggingUserId !== targetId) {
      this.dropTargetUserId = targetId;
      if (ev.dataTransfer) ev.dataTransfer.dropEffect = 'move';
    }
  }

  onDragLeaveNode(ev: DragEvent, targetId: number): void {
    if (this.dropTargetUserId === targetId) {
      this.dropTargetUserId = null;
    }
  }

  onDropOnNode(ev: DragEvent, targetId: number): void {
    ev.preventDefault();
    ev.stopPropagation();
    this.dropTargetUserId = null;
    if (!this.draggingUserId || this.draggingUserId === targetId) return;
    this.assignUser(this.draggingUserId, targetId);
    this.draggingUserId = null;
  }

  onDragEnd(): void {
    this.draggingUserId = null;
    this.dropTargetUserId = null;
  }

  // Drop on empty canvas → make root
  onCanvasDragOver(ev: DragEvent): void {
    ev.preventDefault();
    if (ev.dataTransfer) ev.dataTransfer.dropEffect = 'move';
  }

  onCanvasDrop(ev: DragEvent): void {
    ev.preventDefault();
    if (!this.draggingUserId) return;
    // Only if not dropped on a node
    if (!(ev.target as HTMLElement).closest('.org-node')) {
      this.makeRoot(this.draggingUserId);
    }
    this.draggingUserId = null;
    this.dropTargetUserId = null;
  }

  // ── Assignment API calls ────────────────────────────────────────────────

  assignUser(userId: number, reportTo: number): void {
    this.api.put('/org-tree/assign', { userId, reportTo }).subscribe({
      next: () => {
        const user = this.allUsers.find(u => u.userId === userId);
        if (user) user.reportTo = reportTo;
        this.computeLayout();
        this.notify.success('User assigned');
      },
      error: (err) => this.notify.error(err.error?.detail || 'Assignment failed'),
    });
  }

  makeRoot(userId: number): void {
    // Self-reference convention: reportTo = userId means root
    this.api.put('/org-tree/assign', { userId, reportTo: userId }).subscribe({
      next: () => {
        const user = this.allUsers.find(u => u.userId === userId);
        if (user) user.reportTo = userId;
        this.computeLayout();
        this.notify.success('User set as root');
      },
      error: (err) => this.notify.error(err.error?.detail || 'Failed'),
    });
  }

  unassignUser(userId: number, ev: MouseEvent): void {
    ev.stopPropagation();
    this.api.put('/org-tree/assign', { userId, reportTo: null }).subscribe({
      next: () => {
        const user = this.allUsers.find(u => u.userId === userId);
        if (user) user.reportTo = null;
        // Also unassign all children of this user
        for (const u of this.allUsers) {
          if (u.reportTo === userId) {
            u.reportTo = null;
          }
        }
        this.computeLayout();
        this.notify.success('User removed from tree');
      },
      error: (err) => this.notify.error(err.error?.detail || 'Failed'),
    });
  }

  // ── Pan & Zoom ──────────────────────────────────────────────────────────

  onWheel(ev: WheelEvent): void {
    ev.preventDefault();
    const delta = ev.deltaY > 0 ? -0.08 : 0.08;
    this.scale = Math.min(2, Math.max(0.25, this.scale + delta));
  }

  zoomIn(): void {
    this.scale = Math.min(2, this.scale + 0.15);
  }

  zoomOut(): void {
    this.scale = Math.max(0.25, this.scale - 0.15);
  }

  resetView(): void {
    this.scale = 1;
    this.translateX = 0;
    this.translateY = 0;
  }

  onCanvasMouseDown(ev: MouseEvent): void {
    if ((ev.target as HTMLElement).closest('.org-node')) return;
    if ((ev.target as HTMLElement).closest('.zoom-controls')) return;
    this.isPanning = true;
    this.panStartX = ev.clientX;
    this.panStartY = ev.clientY;
    this.panStartTX = this.translateX;
    this.panStartTY = this.translateY;
  }

  @HostListener('document:mousemove', ['$event'])
  onMouseMove(ev: MouseEvent): void {
    if (!this.isPanning) return;
    this.translateX = this.panStartTX + (ev.clientX - this.panStartX);
    this.translateY = this.panStartTY + (ev.clientY - this.panStartY);
  }

  @HostListener('document:mouseup')
  onMouseUp(): void {
    this.isPanning = false;
  }

  // ── Helpers ─────────────────────────────────────────────────────────────

  getInitial(name: string): string {
    return (name?.charAt(0) || 'U').toUpperCase();
  }

  get canvasTransform(): string {
    return `translate(${this.translateX}px, ${this.translateY}px) scale(${this.scale})`;
  }

  trackUser(index: number, user: OrgUser): number {
    return user.userId;
  }
}
