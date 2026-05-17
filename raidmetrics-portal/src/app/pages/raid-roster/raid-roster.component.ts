import { Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { catchError, forkJoin, of } from 'rxjs';
import { CharacterSelectionService } from '../../services/character-selection.service';
import { Difficulty, RaidRosterService, Role, RosterMember } from '../../services/raid-roster.service';
import { GuildMember, WowService } from '../../services/wow.service';
import { CharacterPanelComponent, PanelCharacter } from '../../components/character-panel/character-panel.component';

interface RostersState {
  normal: RosterMember[];
  heroic: RosterMember[];
  mythic: RosterMember[];
}

const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  normal: 'Normal',
  heroic: 'Heroic',
  mythic: 'Mythic',
};

const ROSTER_LIMITS: Record<Difficulty, number> = {
  normal: 30,
  heroic: 30,
  mythic: 20,
};

@Component({
  selector: 'app-raid-roster',
  imports: [FormsModule, RouterLink, CharacterPanelComponent],
  templateUrl: './raid-roster.component.html',
})
export class RaidRosterComponent {
  readonly selection = inject(CharacterSelectionService);
  private wow = inject(WowService);
  private raidRosterSvc = inject(RaidRosterService);

  readonly char = computed(() => this.selection.selected());
  readonly canEdit = computed(() => {
    const c = this.char();
    return !!c && (c.is_gm || c.is_officer);
  });

  readonly difficulties: Difficulty[] = ['normal', 'heroic', 'mythic'];
  readonly roles: Role[] = ['tank', 'healer', 'dps'];
  readonly difficultyLabels = DIFFICULTY_LABELS;
  readonly rosterLimits = ROSTER_LIMITS;

  readonly activeTab = signal<Difficulty>('mythic');
  readonly rostersLoading = signal(true);
  readonly guildMembersLoading = signal(false);
  readonly saving = signal<Difficulty | null>(null);
  readonly saveError = signal<string | null>(null);
  readonly saveSuccess = signal<Difficulty | null>(null);
  readonly refreshingRoster = signal(false);
  readonly panelChar = signal<PanelCharacter | null>(null);

  readonly rosters = signal<RostersState>({ normal: [], heroic: [], mythic: [] });
  readonly guildMembers = signal<GuildMember[]>([]);
  readonly searchQuery = signal('');

  private readonly _rolePriority: Record<string, number> = { tank: 0, healer: 1, dps: 2 };

  readonly sortedRoster = computed(() =>
    [...this.rosters()[this.activeTab()]].sort((a, b) => {
      const rA = this._rolePriority[a.role ?? ''] ?? 3;
      const rB = this._rolePriority[b.role ?? ''] ?? 3;
      if (rA !== rB) return rA - rB;
      return a.character_name.localeCompare(b.character_name);
    })
  );

  readonly filteredAvailable = computed(() => {
    const q = this.searchQuery().toLowerCase();
    const current = this.rosters()[this.activeTab()];
    const taken = new Set(
      current.map(m => `${m.character_name.toLowerCase()}|${m.character_realm.toLowerCase()}`)
    );
    return this.guildMembers().filter(m => {
      if (taken.has(`${m.name.toLowerCase()}|${m.realm.toLowerCase()}`)) return false;
      return !q || m.name.toLowerCase().includes(q) || m.class.toLowerCase().includes(q);
    });
  });

  constructor() {
    effect(() => {
      const char = this.char();
      if (char?.guild_id && char.guild_realm_slug && char.guild_slug) {
        this._loadAll(char.guild_id, char.guild_realm_slug, char.guild_slug);
      }
    });
  }

  private _loadAll(guildId: number, realmSlug: string, guildSlug: string): void {
    this.rostersLoading.set(true);
    this.guildMembersLoading.set(true);

    this.wow.getGuildRoster(guildId, realmSlug, guildSlug).subscribe({
      next: ({ members }) => {
        this.guildMembers.set(members);
        this.guildMembersLoading.set(false);
      },
      error: () => this.guildMembersLoading.set(false),
    });

    forkJoin({
      normal: this.raidRosterSvc.getRoster(guildId, 'normal').pipe(catchError(() => of({ members: [] }))),
      heroic: this.raidRosterSvc.getRoster(guildId, 'heroic').pipe(catchError(() => of({ members: [] }))),
      mythic: this.raidRosterSvc.getRoster(guildId, 'mythic').pipe(catchError(() => of({ members: [] }))),
    }).subscribe(results => {
      this.rosters.set({
        normal: results.normal.members,
        heroic: results.heroic.members,
        mythic: results.mythic.members,
      });
      this.rostersLoading.set(false);
    });
  }

  addMember(member: GuildMember, role: Role): void {
    const tab = this.activeTab();
    const current = this.rosters();
    if (current[tab].length >= ROSTER_LIMITS[tab]) return;
    const newMember: RosterMember = {
      character_name: member.name,
      character_realm: member.realm,
      character_class: member.class,
      role,
      sort_order: current[tab].length,
    };
    this.rosters.set({ ...current, [tab]: [...current[tab], newMember] });
    this.searchQuery.set('');
  }

  readonly roleLabel: Record<Role, string> = { tank: 'Tank', healer: 'Healer', dps: 'DPS' };
  readonly roleClass: Record<Role, string> = {
    tank:   'text-blue-400 bg-blue-400/10',
    healer: 'text-green-400 bg-green-400/10',
    dps:    'text-red-400 bg-red-400/10',
  };

  private readonly classRoles: Record<string, Role[]> = {
    'Death Knight': ['tank', 'dps'],
    'Demon Hunter': ['tank', 'dps'],
    'Druid':        ['tank', 'healer', 'dps'],
    'Evoker':       ['healer', 'dps'],
    'Hunter':       ['dps'],
    'Mage':         ['dps'],
    'Monk':         ['tank', 'healer', 'dps'],
    'Paladin':      ['tank', 'healer', 'dps'],
    'Priest':       ['healer', 'dps'],
    'Rogue':        ['dps'],
    'Shaman':       ['healer', 'dps'],
    'Warlock':      ['dps'],
    'Warrior':      ['tank', 'dps'],
  };

  toRealmSlug(realm: string): string {
    return realm.toLowerCase().replace(/'/g, '').replace(/\s+/g, '-');
  }

  availableRoles(member: GuildMember): Role[] {
    return this.classRoles[member.class] ?? this.roles;
  }

  removeMember(difficulty: Difficulty, name: string, realm: string): void {
    const current = this.rosters();
    this.rosters.set({
      ...current,
      [difficulty]: current[difficulty].filter(
        m => !(m.character_name === name && m.character_realm === realm)
      ),
    });
  }

  saveRoster(difficulty: Difficulty): void {
    const char = this.char();
    if (!char?.guild_id) return;
    this.saving.set(difficulty);
    this.saveError.set(null);
    this.saveSuccess.set(null);
    const members = this.rosters()[difficulty].map((m, i) => ({ ...m, sort_order: i }));
    this.raidRosterSvc.updateRoster(char.guild_id, difficulty, members).subscribe({
      next: ({ members: saved }) => {
        const current = this.rosters();
        this.rosters.set({ ...current, [difficulty]: saved });
        this.saving.set(null);
        this.saveSuccess.set(difficulty);
        setTimeout(() => this.saveSuccess.set(null), 3000);
      },
      error: () => {
        this.saving.set(null);
        this.saveError.set('Failed to save roster. Please try again.');
      },
    });
  }

  setTab(tab: Difficulty): void {
    this.activeTab.set(tab);
    this.searchQuery.set('');
  }

  refreshGuildRoster(): void {
    const char = this.char();
    if (!char?.guild_id || !char.guild_realm_slug || !char.guild_slug) return;
    this.refreshingRoster.set(true);
    this.wow.refreshGuildRoster(char.guild_id, char.guild_realm_slug, char.guild_slug).subscribe({
      next: ({ members }) => {
        this.guildMembers.set(members);
        this.refreshingRoster.set(false);
      },
      error: () => this.refreshingRoster.set(false),
    });
  }
}
