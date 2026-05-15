import { Component, OnInit, inject } from '@angular/core';
import { Router } from '@angular/router';
import { BattlenetAuthService } from '../../services/battlenet-auth.service';
import { SessionService } from '../../services/session.service';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss'
})
export class LoginComponent implements OnInit {
  private battlenet = inject(BattlenetAuthService);
  private session = inject(SessionService);
  private router = inject(Router);

  ngOnInit(): void {
    if (this.session.isLoggedIn()) {
      this.router.navigate(['/dashboard']);
    }
  }

  loginWithBattleNet(): void {
    this.battlenet.getLoginRedirectUrl().subscribe(({ url, state }) => {
      sessionStorage.setItem('oauth_state', state);
      window.location.href = url;
    });
  }
}
