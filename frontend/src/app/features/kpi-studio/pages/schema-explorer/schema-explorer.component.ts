import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatChipsModule } from '@angular/material/chips';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatExpansionModule } from '@angular/material/expansion';

import { KpiSchemaService } from '../../services/kpi-schema.service';
import { NotificationService } from '../../../../core/services/notification.service';
import {
  SchemaGraph,
  SchemaListResponse,
  TableInfo,
  TableRelationship,
  TableRelationshipCreate,
} from '../../models/schema.types';

@Component({
  selector: 'app-kpi-schema-explorer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatIconModule,
    MatTabsModule,
    MatChipsModule,
    MatTooltipModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
    MatExpansionModule,
  ],
  templateUrl: './schema-explorer.component.html',
  styleUrls: ['./schema-explorer.component.scss'],
})
export class SchemaExplorerComponent implements OnInit {
  private readonly schemaService = inject(KpiSchemaService);
  private readonly notify = inject(NotificationService);
  private readonly destroyRef = inject(DestroyRef);

  // ---- state ------------------------------------------------------------
  readonly loading = signal(false);
  readonly refreshing = signal(false);
  readonly snapshot = signal<SchemaListResponse | null>(null);
  readonly graph = signal<SchemaGraph | null>(null);
  readonly searchTerm = signal('');
  readonly selectedTableId = signal<string | null>(null);

  // ---- derived ----------------------------------------------------------
  readonly tables = computed<TableInfo[]>(() => this.snapshot()?.tables ?? []);
  readonly meta = computed(() => this.snapshot()?.snapshot ?? null);

  readonly filteredTables = computed(() => {
    const q = this.searchTerm().trim().toLowerCase();
    const tables = this.tables();
    if (!q) return tables;
    return tables.filter(t =>
      t.name.toLowerCase().includes(q) ||
      t.columns.some(c => c.name.toLowerCase().includes(q)),
    );
  });

  readonly selectedTable = computed<TableInfo | null>(() => {
    const id = this.selectedTableId();
    if (!id) return null;
    return this.tables().find(t => this.tableId(t) === id) ?? null;
  });

  // ---- ER diagram layout (simple grid; Phase 2 swaps to vis-network) ---
  readonly graphLayout = computed(() => {
    const g = this.graph();
    if (!g) return null;

    const cols = Math.ceil(Math.sqrt(g.nodes.length || 1));
    const cellW = 200;
    const cellH = 110;
    const positions = new Map<string, { x: number; y: number }>();
    g.nodes.forEach((node, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      positions.set(node.id, {
        x: col * cellW + cellW / 2,
        y: row * cellH + cellH / 2,
      });
    });

    return {
      width: cols * cellW,
      height: Math.ceil(g.nodes.length / cols) * cellH,
      nodes: g.nodes.map(n => ({ ...n, ...positions.get(n.id)! })),
      edges: g.edges
        .map(e => ({
          ...e,
          from: positions.get(e.source),
          to: positions.get(e.target),
        }))
        .filter(e => e.from && e.to),
    };
  });

  // ---- Phase F — relationships state ----------------------------------
  readonly relationships = signal<TableRelationship[]>([]);
  readonly loadingRels = signal(false);
  readonly seedingRels = signal(false);
  readonly newRel = signal<TableRelationshipCreate>({
    from_table: '', from_column: '', to_table: '', to_column: '',
    cardinality: 'many_to_one',
  });

  patchNewRel(key: keyof TableRelationshipCreate, value: any): void {
    this.newRel.update(s => ({ ...s, [key]: value }));
  }

  canCreateRel = computed(() => {
    const r = this.newRel();
    return !!r.from_table && !!r.from_column && !!r.to_table && !!r.to_column;
  });

  ngOnInit(): void {
    this.loadAll();
    this.loadRelationships();
  }

  loadRelationships(): void {
    this.loadingRels.set(true);
    this.schemaService.listRelationships()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.relationships.set(res.items);
          this.loadingRels.set(false);
        },
        error: err => {
          this.loadingRels.set(false);
          this.notify.error(err?.error?.detail ?? 'Failed to load relationships');
        },
      });
  }

  autoSeedRelationships(): void {
    this.seedingRels.set(true);
    this.schemaService.autoSeedRelationships()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.seedingRels.set(false);
          this.notify.success(
            `Inserted ${res.inserted} new edge${res.inserted === 1 ? '' : 's'} ` +
            `(${res.skipped} unchanged, ${res.total_active} active total).`,
          );
          this.loadRelationships();
        },
        error: err => {
          this.seedingRels.set(false);
          this.notify.error(err?.error?.detail ?? 'Auto-seed failed');
        },
      });
  }

  createRelationship(): void {
    const r = this.newRel();
    if (!this.canCreateRel()) return;
    this.schemaService.createRelationship(r)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.notify.success('Relationship added.');
          this.newRel.set({
            from_table: '', from_column: '', to_table: '', to_column: '',
            cardinality: 'many_to_one',
          });
          this.loadRelationships();
        },
        error: err => this.notify.error(err?.error?.detail ?? 'Create failed'),
      });
  }

  deleteRelationship(rel: TableRelationship): void {
    this.schemaService.deleteRelationship(rel.relationship_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.notify.success('Relationship removed.');
          this.loadRelationships();
        },
        error: err => this.notify.error(err?.error?.detail ?? 'Delete failed'),
      });
  }

  // ---- actions ----------------------------------------------------------

  loadAll(): void {
    this.loading.set(true);
    this.schemaService
      .getTables()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.snapshot.set(res);
          this.loading.set(false);
          this.loadGraph();
        },
        error: err => {
          this.loading.set(false);
          this.notify.error(err?.error?.detail ?? 'Failed to load schema');
        },
      });
  }

  loadGraph(): void {
    this.schemaService
      .getGraph()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: g => this.graph.set(g),
        error: () => {/* silent — graph is optional */},
      });
  }

  refresh(): void {
    this.refreshing.set(true);
    this.schemaService
      .refresh()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.refreshing.set(false);
          this.notify.success('Schema re-introspected');
          this.loadAll();
        },
        error: err => {
          this.refreshing.set(false);
          this.notify.error(err?.error?.detail ?? 'Refresh failed');
        },
      });
  }

  selectTable(t: TableInfo): void {
    this.selectedTableId.set(this.tableId(t));
  }

  selectTableById(id: string): void {
    this.selectedTableId.set(id);
  }

  tableId(t: TableInfo): string {
    return t.schema ? `${t.schema}.${t.name}` : t.name;
  }

  trackTable = (_: number, t: TableInfo) => this.tableId(t);
}
