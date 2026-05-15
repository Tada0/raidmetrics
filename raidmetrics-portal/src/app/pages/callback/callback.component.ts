import { Component, OnInit, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ActivatedRoute, Router } from '@angular/router';
import { BlizzardAuthService } from '../../services/blizzard-auth.service';

@Component({
  selector: 'app-callback',
  imports: [RouterLink],
  templateUrl: './callback.component.html',
})
export class CallbackComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private authService = inject(BlizzardAuthService);

  error = '';

  ngOnInit(): void {
    const code = this.route.snapshot.queryParamMap.get('code');
    const state = this.route.snapshot.queryParamMap.get('state');
    const storedState = sessionStorage.getItem('oauth_state');

    if (!code || !state) {
      this.error = 'Invalid callback: missing code or state.';
      return;
    }

    if (state !== storedState) {
      this.error = 'State mismatch — possible CSRF attempt.';
      return;
    }

    sessionStorage.removeItem('oauth_state');

    this.authService.exchangeCode(code).subscribe({
      next: () => {
        const returnTo = sessionStorage.getItem('returnTo') ?? '/dashboard';
        sessionStorage.removeItem('returnTo');
        this.router.navigateByUrl(returnTo);
      },
      error: () => { this.error = 'Login failed. Please try again.'; },
    });
  }
}
