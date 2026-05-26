import { Routes } from '@angular/router';

// Phase A2 — dashboards land first; KPI library + schema explorer remain.
export const KPI_STUDIO_ROUTES: Routes = [
  { path: '', redirectTo: 'dashboards', pathMatch: 'full' },

  // Dashboards
  {
    path: 'dashboards',
    loadComponent: () =>
      import('./pages/dashboards-list/dashboards-list.component')
        .then(m => m.DashboardsListComponent),
  },
  {
    path: 'dashboards/:id',
    loadComponent: () =>
      import('./pages/dashboard-view/dashboard-view.component')
        .then(m => m.DashboardViewComponent),
  },
  {
    path: 'dashboards/:id/edit',
    loadComponent: () =>
      import('./pages/dashboard-view/dashboard-view.component')
        .then(m => m.DashboardViewComponent),
    data: { mode: 'edit' },
  },

  // KPI library
  {
    path: 'kpis',
    loadComponent: () =>
      import('./pages/kpi-list/kpi-list.component').then(m => m.KpiListComponent),
  },
  {
    path: 'kpis/new',
    loadComponent: () =>
      import('./pages/kpi-editor/kpi-editor.component').then(m => m.KpiEditorComponent),
  },
  {
    path: 'kpis/:id',
    loadComponent: () =>
      import('./pages/kpi-editor/kpi-editor.component').then(m => m.KpiEditorComponent),
  },

  // SuperAdmin diagnostic
  {
    path: 'schema',
    loadComponent: () =>
      import('./pages/schema-explorer/schema-explorer.component')
        .then(m => m.SchemaExplorerComponent),
  },

  // SuperAdmin settings (LLM provider, API key, agent caps)
  {
    path: 'settings',
    loadComponent: () =>
      import('./pages/settings/settings.component')
        .then(m => m.SettingsComponent),
  },

  // Smart-analysis chatbot (Phase B1) — chat-with-DB via the A7 agent.
  {
    path: 'chat',
    loadComponent: () =>
      import('./pages/chat/chat.component')
        .then(m => m.ChatPageComponent),
  },

  // Eval harness admin (T-001). SuperAdmin only — backend gated to
  // kpi:settings and the menu entry is hidden by the has-permission
  // directive for everyone else.
  {
    path: 'eval',
    loadComponent: () =>
      import('./pages/eval/eval-page.component')
        .then(m => m.EvalPageComponent),
  },

  // Scheduled jobs admin (T-003). SuperAdmin only — same gate as eval.
  {
    path: 'jobs',
    loadComponent: () =>
      import('./pages/jobs/jobs-page.component')
        .then(m => m.JobsPageComponent),
  },
];
