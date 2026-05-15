import { inject } from '@angular/core';
import { HttpInterceptorFn } from '@angular/common/http';
import { SessionService } from '../services/session.service';
import { environment } from '../../environments/environment';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith('/api/')) return next(req);

  const headers: Record<string, string> = {
    'X-Frontend-Auth': environment.frontendSecret,
  };

  const token = inject(SessionService).token();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  req = req.clone({ setHeaders: headers });
  return next(req);
};
