import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
}

@Injectable({ providedIn: 'root' })
export class SessionService {
  private http = inject(HttpClient);

  private _token = signal<string | null>(null);
  readonly isLoggedIn = computed(() => this._token() !== null);
  readonly token = this._token.asReadonly();

  setToken(token: string): void {
    this._token.set(token);
  }

  refresh(): Observable<AuthResponse> {
    return this.http.post<AuthResponse>('/api/v1/auth/session/refresh', {}).pipe(
      tap(res => this._token.set(res.access_token))
    );
  }

  logout(): Observable<void> {
    return this.http.post<void>('/api/v1/auth/session/logout', {}).pipe(
      tap(() => this._token.set(null))
    );
  }
}
