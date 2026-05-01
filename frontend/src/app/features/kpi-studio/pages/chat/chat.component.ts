import { ChangeDetectionStrategy, Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChatPanelComponent } from '../../components/chat-panel/chat-panel.component';

/**
 * Full-screen chat page at /kpi-studio/chat. Wraps the reusable
 * ChatPanelComponent in a page chrome so the same UI works for both
 * the dedicated route and the dashboard slide-out (which sets
 * ``compact=true``).
 */
@Component({
  selector: 'app-kpi-chat-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, ChatPanelComponent],
  template: `
    <div class="page">
      <header class="page-header">
        <h1>Smart Analysis</h1>
        <p class="hint">
          Ask questions about your data; the agent inspects the schema,
          writes SQL, runs it, and shows you the result. History is
          retained per chat — start a new one for unrelated topics.
        </p>
      </header>
      <div class="panel-wrap">
        <app-chat-panel></app-chat-panel>
      </div>
    </div>
  `,
  styles: [`
    /* Pin the page to the viewport (toolbar 64px + content-area
       1.5rem top/bottom padding = 64+48px) so the inner messages list
       scrolls instead of the whole page — chat-style layout. */
    :host { display: block; height: 100%; }
    .page {
      display: flex; flex-direction: column;
      height: calc(100vh - 64px - 3rem);
      padding: 16px 24px 24px;
      box-sizing: border-box;
      overflow: hidden;
    }
    .page-header {
      flex: 0 0 auto;
      width: 100%;
      max-width: 1400px;
      margin: 0 auto;
      h1 {
        margin: 0; font-size: 1.4rem; color: var(--snm-text-primary);
      }
      .hint {
        margin: 4px 0 12px; color: var(--snm-text-muted);
        font-size: 0.85rem; max-width: 680px;
      }
    }
    /* Cap the chat at a comfortable reading width on wide monitors and
       centre it. Block layout (not flex) so the inner chat-panel's
       width:100% / height:100% reliably fills the wrap — flex-basis
       quirks were leaving the conversation column shrunk to its
       intrinsic content width. */
    .panel-wrap {
      flex: 1 1 auto; min-height: 0;
      width: 100%;
      max-width: 1400px;
      margin: 0 auto;
    }
  `],
})
export class ChatPageComponent {}
