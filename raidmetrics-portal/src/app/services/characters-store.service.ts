import { Injectable, inject, signal } from '@angular/core';
import { catchError, of, tap } from 'rxjs';
import { CharacterSelectionService } from './character-selection.service';
import { WowCharacter, WowService } from './wow.service';

interface CharactersState {
  loading: boolean;
  characters: WowCharacter[];
  error: string;
}

const INITIAL: CharactersState = { loading: true, characters: [], error: '' };

@Injectable({ providedIn: 'root' })
export class CharactersStore {
  private wow = inject(WowService);
  private selection = inject(CharacterSelectionService);

  private _state = signal<CharactersState>(INITIAL);
  readonly state = this._state.asReadonly();

  private _loaded = false;

  load(): void {
    if (this._loaded) return;
    this._loaded = true;

    this.wow.getCharacters().pipe(
      tap(({ characters }) => {
        this._state.set({ loading: false, characters, error: '' });
        this.selection.tryRestoreFrom(characters);
      }),
      catchError(() => {
        this._state.set({ loading: false, characters: [], error: 'Failed to load characters.' });
        return of(null);
      }),
    ).subscribe();
  }
}
