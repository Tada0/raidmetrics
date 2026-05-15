import { Injectable, signal } from '@angular/core';
import { WowCharacter } from './wow.service';

@Injectable({ providedIn: 'root' })
export class CharacterSelectionService {
  private readonly STORAGE_KEY = 'raidmetrics.selectedCharacter';

  private _selected = signal<WowCharacter | null>(null);
  readonly selected = this._selected.asReadonly();

  select(char: WowCharacter): void {
    this._selected.set(char);
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify({ name: char.name, realm: char.realm }));
  }

  tryRestoreFrom(characters: WowCharacter[]): void {
    const raw = localStorage.getItem(this.STORAGE_KEY);
    if (!raw) return;
    try {
      const { name, realm } = JSON.parse(raw);
      const match = characters.find(c => c.name === name && c.realm === realm);
      if (match) this._selected.set(match);
      else localStorage.removeItem(this.STORAGE_KEY);
    } catch {
      localStorage.removeItem(this.STORAGE_KEY);
    }
  }

  clear(): void {
    this._selected.set(null);
    localStorage.removeItem(this.STORAGE_KEY);
  }
}
