import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { BlizzardAuthService } from '../services/blizzard-auth.service';

export const authGuard: CanActivateFn = () => {
  const auth = inject(BlizzardAuthService);
  const router = inject(Router);
  return auth.isLoggedIn() || router.createUrlTree(['/']);
};
