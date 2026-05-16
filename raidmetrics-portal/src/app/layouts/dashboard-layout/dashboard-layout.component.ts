import { DatePipe } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { CharacterSelectionService } from '../../services/character-selection.service';
import { CharactersStore } from '../../services/characters-store.service';
import { ScraperService } from '../../services/scraper.service';
import { SessionService } from '../../services/session.service';

@Component({
  selector: 'app-dashboard-layout',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, DatePipe],
  templateUrl: './dashboard-layout.component.html',
})
export class DashboardLayoutComponent {
  private session = inject(SessionService);
  private router = inject(Router);
  private store = inject(CharactersStore);
  readonly selection = inject(CharacterSelectionService);
  readonly scraper = inject(ScraperService);

  readonly isPrivileged = computed(() =>
    this.store.state().characters.some(c => c.is_gm || c.is_officer)
  );

  constructor() {
    this.store.load();
    this.scraper.loadStatus();
  }

  logout(): void {
    this.session.logout().subscribe(() => this.router.navigate(['/']));
  }
}
