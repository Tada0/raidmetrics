import { inject } from '@angular/core';
import { HttpInterceptorFn } from '@angular/common/http';
import { BlizzardAuthService } from '../services/blizzard-auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith('/api/')) return next(req);

  const token = inject(BlizzardAuthService).token();
  if (token) {
    req = req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
  }
  return next(req);
};
