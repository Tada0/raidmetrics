import { Component, effect, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { catchError, map, of, startWith } from 'rxjs';
import { CharacterSelectionService } from '../../services/character-selection.service';
import { WowService, WowCharacter } from '../../services/wow.service';

interface DashboardState {
  loading: boolean;
  characters: WowCharacter[];
  error: string;
}

const LOADING: DashboardState = { loading: true, characters: [], error: '' };

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent {
  private wow = inject(WowService);
  readonly selection = inject(CharacterSelectionService);

  state = toSignal(
    this.wow.getCharacters().pipe(
      map(({ characters }): DashboardState => ({ loading: false, characters, error: '' })),
      catchError(() => of<DashboardState>({ loading: false, characters: [], error: 'Failed to load characters.' })),
      startWith(LOADING),
    ),
    { initialValue: LOADING }
  );

  constructor() {
    effect(() => {
      const { loading, characters } = this.state();
      if (!loading && characters.length) {
        this.selection.tryRestoreFrom(characters);
      }
    });
  }

  select(char: WowCharacter): void {
    this.selection.select(char);
  }

  isSelected(char: WowCharacter): boolean {
    const s = this.selection.selected();
    return !!s && s.name === char.name && s.realm === char.realm;
  }
}
