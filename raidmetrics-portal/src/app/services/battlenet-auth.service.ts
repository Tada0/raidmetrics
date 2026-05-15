import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';
import { SessionService, AuthResponse } from './session.service';

interface LoginRedirectUrlResponse {
  state: string;
  url: string;
}

@Injectable({ providedIn: 'root' })
export class BattlenetAuthService {
  private http = inject(HttpClient);
  private session = inject(SessionService);

  getLoginRedirectUrl(): Observable<LoginRedirectUrlResponse> {
    return this.http.get<LoginRedirectUrlResponse>('/api/v1/auth/battlenet/login_redirect_url');
  }

  exchangeCode(code: string): Observable<AuthResponse> {
    return this.http.post<AuthResponse>('/api/v1/auth/battlenet/callback', { code }).pipe(
      tap(res => this.session.setToken(res.access_token))
    );
  }
}
