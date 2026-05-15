import { Component, OnInit, inject } from '@angular/core';
import { Router } from '@angular/router';
import { BlizzardAuthService } from '../../services/blizzard-auth.service';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss'
})
export class LoginComponent implements OnInit {
  private authService = inject(BlizzardAuthService);
  private router = inject(Router);

  ngOnInit(): void {
    if (this.authService.isLoggedIn()) {
      this.router.navigate(['/dashboard']);
    }
  }

  loginWithBattleNet(): void {
    this.authService.getLoginRedirectUrl().subscribe(({ url, state }) => {
      sessionStorage.setItem('oauth_state', state);
      window.location.href = url;
    });
  }
}
