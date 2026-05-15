import { Component, inject } from '@angular/core';
import { CharacterSelectionService } from '../../services/character-selection.service';
import { CharactersStore } from '../../services/characters-store.service';
import { WowCharacter } from '../../services/wow.service';

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent {
  readonly selection = inject(CharacterSelectionService);
  readonly store = inject(CharactersStore);

  get state() { return this.store.state; }

  select(char: WowCharacter): void {
    this.selection.select(char);
  }

  isSelected(char: WowCharacter): boolean {
    const s = this.selection.selected();
    return !!s && s.name === char.name && s.realm === char.realm;
  }
}
