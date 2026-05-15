import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface WowCharacter {
  name: string;
  realm: string;
  class: string;
  race: string;
  level: number;
  faction: string;
  guild: string | null;
  guild_rank: number | null;
  is_gm: boolean;
  is_officer: boolean;
}

@Injectable({ providedIn: 'root' })
export class WowService {
  private http = inject(HttpClient);

  getCharacters(): Observable<{ characters: WowCharacter[] }> {
    return this.http.get<{ characters: WowCharacter[] }>('/api/v1/wow/characters');
  }
}
