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
  guild_id: number | null;
  guild_realm_slug: string | null;
  guild_slug: string | null;
  guild_rank: number | null;
  is_gm: boolean;
  is_officer: boolean;
}

export interface GuildMember {
  name: string;
  realm: string;
  realm_slug: string;
  class: string;
  level: number;
  rank: number;
  is_gm: boolean;
  is_officer: boolean;
}

@Injectable({ providedIn: 'root' })
export class WowService {
  private http = inject(HttpClient);

  getCharacters(): Observable<{ characters: WowCharacter[] }> {
    return this.http.get<{ characters: WowCharacter[] }>('/api/v1/wow/characters');
  }

  getGuildRoster(guildId: number, guildRealmSlug: string, guildSlug: string): Observable<{ members: GuildMember[] }> {
    return this.http.get<{ members: GuildMember[] }>('/api/v1/wow/guild-roster', {
      params: { guild_id: guildId, guild_realm_slug: guildRealmSlug, guild_slug: guildSlug },
    });
  }
}
