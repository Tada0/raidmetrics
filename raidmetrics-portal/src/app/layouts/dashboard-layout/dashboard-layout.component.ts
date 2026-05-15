import { Component, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { CharacterSelectionService } from '../../services/character-selection.service';
import { SessionService } from '../../services/session.service';

@Component({
  selector: 'app-dashboard-layout',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './dashboard-layout.component.html',
})
export class DashboardLayoutComponent {
  private session = inject(SessionService);
  private router = inject(Router);
  readonly selection = inject(CharacterSelectionService);

  logout(): void {
    this.session.logout().subscribe(() => this.router.navigate(['/']));
  }
}
