import { ApplicationConfig, inject, provideAppInitializer, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { authInterceptor } from './interceptors/auth.interceptor';
import { battlenetTokenInterceptor } from './interceptors/battlenet-token.interceptor';
import { firstValueFrom, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { routes } from './app.routes';
import { SessionService } from './services/session.service';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor, battlenetTokenInterceptor])),
    provideAppInitializer(() => {
      const session = inject(SessionService);
      return firstValueFrom(session.refresh().pipe(catchError(() => of(null))));
    }),
  ]
};
