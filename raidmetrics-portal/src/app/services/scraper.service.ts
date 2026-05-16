import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';

export interface ScrapeRun {
  id: number;
  started_at: string;
  completed_at: string | null;
  success: boolean;
  specs_scraped: number;
  error_message: string | null;
}

export interface ScrapeStatus {
  running: boolean;
  total_specs: number;
  last_run: ScrapeRun | null;
}

@Injectable({ providedIn: 'root' })
export class ScraperService {
  private http = inject(HttpClient);

  readonly status = signal<ScrapeStatus | null>(null);
  readonly triggering = signal(false);

  private _pollInterval: ReturnType<typeof setInterval> | null = null;

  loadStatus(): void {
    this.http.get<ScrapeStatus>('/api/v1/scraper/status').subscribe({
      next: s => {
        this.status.set(s);
        if (s.running) this._startPolling();
        else this._stopPolling();
      },
      error: () => {},
    });
  }

  trigger(): void {
    if (this.triggering()) return;
    this.triggering.set(true);
    this.http.post<{ started: boolean }>('/api/v1/scraper/trigger', {}).subscribe({
      next: () => {
        this.triggering.set(false);
        this.loadStatus();
        this._startPolling();
      },
      error: () => this.triggering.set(false),
    });
  }

  private _startPolling(): void {
    if (this._pollInterval) return;
    this._pollInterval = setInterval(() => this.loadStatus(), 3000);
  }

  private _stopPolling(): void {
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
    }
  }
}
