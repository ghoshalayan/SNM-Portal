import { Injectable, signal, effect } from '@angular/core';

export type ThemeMode = 'light' | 'dark';

const STORAGE_KEY = 'snm-theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly mode = signal<ThemeMode>(this.loadSaved());

  constructor() {
    effect(() => this.applyTheme(this.mode()));
  }

  toggle(): void {
    this.mode.set(this.mode() === 'light' ? 'dark' : 'light');
  }

  isDark(): boolean {
    return this.mode() === 'dark';
  }

  private loadSaved(): ThemeMode {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'dark' || saved === 'light') return saved;
    return 'light';
  }

  private applyTheme(mode: ThemeMode): void {
    localStorage.setItem(STORAGE_KEY, mode);
    const body = document.body;
    if (mode === 'dark') {
      body.classList.add('dark-theme');
      body.classList.remove('light-theme');
    } else {
      body.classList.add('light-theme');
      body.classList.remove('dark-theme');
    }
  }
}
