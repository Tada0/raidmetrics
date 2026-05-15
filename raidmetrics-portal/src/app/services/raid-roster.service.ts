import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export type Difficulty = 'normal' | 'heroic' | 'mythic';

export interface RosterMember {
  character_name: string;
  character_realm: string;
  character_class: string | null;
  sort_order: number;
}

@Injectable({ providedIn: 'root' })
export class RaidRosterService {
  private http = inject(HttpClient);

  getRoster(guildId: number, difficulty: Difficulty): Observable<{ members: RosterMember[] }> {
    return this.http.get<{ members: RosterMember[] }>(`/api/v1/raid-roster/${guildId}/${difficulty}`);
  }

  updateRoster(guildId: number, difficulty: Difficulty, members: RosterMember[]): Observable<{ members: RosterMember[] }> {
    return this.http.put<{ members: RosterMember[] }>(`/api/v1/raid-roster/${guildId}/${difficulty}`, { members });
  }
}
