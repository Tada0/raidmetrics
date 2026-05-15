import { inject } from '@angular/core';
import { HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';
import { Router } from '@angular/router';
import { BlizzardAuthService } from '../services/blizzard-auth.service';

export const blizzardTokenInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith('/api/v1/wow/')) return next(req);

  const auth = inject(BlizzardAuthService);
  const router = inject(Router);

  return next(req).pipe(
    catchError(err => {
      if (err.status === 401 && err.error?.detail === 'blizzard_token_expired') {
        sessionStorage.setItem('returnTo', router.url);
        auth.getLoginRedirectUrl().subscribe(({ url, state }) => {
          sessionStorage.setItem('oauth_state', state);
          window.location.href = url;
        });
      }
      return throwError(() => err);
    })
  );
};
