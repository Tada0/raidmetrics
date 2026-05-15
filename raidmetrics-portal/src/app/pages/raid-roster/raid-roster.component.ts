import { Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { catchError, forkJoin, of } from 'rxjs';
import { CharacterSelectionService } from '../../services/character-selection.service';
import { Difficulty, RaidRosterService, RosterMember } from '../../services/raid-roster.service';
import { GuildMember, WowService } from '../../services/wow.service';

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

@Component({
  selector: 'app-raid-roster',
  imports: [FormsModule, RouterLink],
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
  readonly difficultyLabels = DIFFICULTY_LABELS;

  readonly activeTab = signal<Difficulty>('normal');
  readonly rostersLoading = signal(true);
  readonly guildMembersLoading = signal(false);
  readonly saving = signal<Difficulty | null>(null);
  readonly saveError = signal<string | null>(null);

  readonly rosters = signal<RostersState>({ normal: [], heroic: [], mythic: [] });
  readonly guildMembers = signal<GuildMember[]>([]);
  readonly searchQuery = signal('');

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

  addMember(member: GuildMember): void {
    const tab = this.activeTab();
    const current = this.rosters();
    const newMember: RosterMember = {
      character_name: member.name,
      character_realm: member.realm,
      character_class: member.class,
      sort_order: current[tab].length,
    };
    this.rosters.set({ ...current, [tab]: [...current[tab], newMember] });
    this.searchQuery.set('');
  }

  removeMember(difficulty: Difficulty, index: number): void {
    const current = this.rosters();
    this.rosters.set({ ...current, [difficulty]: current[difficulty].filter((_, i) => i !== index) });
  }

  saveRoster(difficulty: Difficulty): void {
    const char = this.char();
    if (!char?.guild_id) return;
    this.saving.set(difficulty);
    this.saveError.set(null);
    const members = this.rosters()[difficulty].map((m, i) => ({ ...m, sort_order: i }));
    this.raidRosterSvc.updateRoster(char.guild_id, difficulty, members).subscribe({
      next: ({ members: saved }) => {
        const current = this.rosters();
        this.rosters.set({ ...current, [difficulty]: saved });
        this.saving.set(null);
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
}
