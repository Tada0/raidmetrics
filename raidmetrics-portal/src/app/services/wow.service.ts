import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, switchMap } from 'rxjs';

export interface WowCharacter {
  name: string;
  realm: string;
  realm_slug: string;
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

export interface CharacterItem {
  slot: string;
  slot_type: string;
  name: string;
  item_id: number;
  item_level: number;
  quality: string;
  bonus_ids: number[];
  enchantment_id: number | null;
  gem_ids: number[];
  crafted_stats: number[];
  icon_url: string | null;
}

export interface CharacterStats {
  health: number;
  stamina: number;
  strength: number;
  agility: number;
  intellect: number;
  crit_rating: number;
  crit_percent: number;
  haste_rating: number;
  haste_percent: number;
  mastery_rating: number;
  mastery_percent: number;
  versatility_rating: number;
  versatility_percent: number;
}

export interface CharacterDetail {
  name: string;
  realm: string;
  level: number;
  faction: string;
  class: string;
  race: string;
  spec: string | null;
  guild: string | null;
  average_item_level: number;
  equipped_item_level: number;
  avatar_url: string | null;
  inset_url: string | null;
  main_raw_url: string | null;
  items: CharacterItem[];
  stats: CharacterStats | null;
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

interface GearCheckResult {
  pass: boolean;
  failing: string[];
  na: boolean;
}

export interface GearCheckPolicy {
  any: GearCheckResult;
  top3: GearCheckResult;
}

export interface CharacterGearCheck {
  name: string;
  spec: string | null;
  class: string;
  equipped_item_level: number;
  spec_found: boolean;
  enchants: GearCheckPolicy;
  gems: GearCheckPolicy;
  embellishments: GearCheckPolicy;
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

  getCharacterDetail(realmSlug: string, characterName: string): Observable<CharacterDetail> {
    return this.http.get<CharacterDetail>('/api/v1/wow/character-detail', {
      params: { realm_slug: realmSlug, character_name: characterName },
    });
  }

  getCharacterGearCheck(realmSlug: string, characterName: string): Observable<CharacterGearCheck> {
    return this.http.get<CharacterGearCheck>('/api/v1/wow/character-gear-check', {
      params: { realm_slug: realmSlug, character_name: characterName },
    });
  }

  refreshGuildRoster(guildId: number, guildRealmSlug: string, guildSlug: string): Observable<{ members: GuildMember[] }> {
    return this.http.delete<void>(`/api/v1/wow/guild-roster-cache/${guildId}`).pipe(
      switchMap(() => this.getGuildRoster(guildId, guildRealmSlug, guildSlug)),
    );
  }
}
