import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';

interface LoginRedirectUrlResponse {
  state: string;
  url: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
}

@Injectable({ providedIn: 'root' })
export class BlizzardAuthService {
  private http = inject(HttpClient);

  private _token = signal<string | null>(null);
  readonly isLoggedIn = computed(() => this._token() !== null);
  readonly token = this._token.asReadonly();

  getLoginRedirectUrl(): Observable<LoginRedirectUrlResponse> {
    return this.http.get<LoginRedirectUrlResponse>('/api/v1/auth/blizzard/login_redirect_url');
  }

  exchangeCode(code: string): Observable<AuthResponse> {
    return this.http.post<AuthResponse>('/api/v1/auth/blizzard/callback', { code }).pipe(
      tap(res => this._token.set(res.access_token))
    );
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
