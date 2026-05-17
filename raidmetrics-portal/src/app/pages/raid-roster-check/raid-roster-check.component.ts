import { Component, computed, effect, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { TitleCasePipe } from '@angular/common';
import { CharacterSelectionService } from '../../services/character-selection.service';
import { CharacterPanelComponent, PanelCharacter } from '../../components/character-panel/character-panel.component';

type EnchantPolicy = 'none' | 'any' | 'top3';
type GemPolicy = 'none' | 'any' | 'top_gems';
type EmbellishPolicy = 'none' | 'any' | 'top3';
type Difficulty = 'normal' | 'heroic' | 'mythic';

interface CriterionResult {
  pass: boolean;
  failing: string[];
  na: boolean;
}

interface MemberResult {
  name: string;
  realm: string;
  role: 'tank' | 'healer' | 'dps' | null;
  spec: string | null;
  class: string;
  equipped_item_level: number;
  ilvl: { pass: boolean };
  enchants: CriterionResult;
  gems: CriterionResult;
  embellishments: CriterionResult;
}

interface CachedCheck {
  results: MemberResult[];
  ranEnchantPolicy: EnchantPolicy;
  ranGemPolicy: GemPolicy;
  ranEmbellishPolicy: EmbellishPolicy;
  minIlvl: number;
  checkedAt: string;
}

@Component({
  selector: 'app-raid-roster-check',
  imports: [FormsModule, TitleCasePipe, CharacterPanelComponent],
  templateUrl: './raid-roster-check.component.html',
})
export class RaidRosterCheckComponent {
  private http = inject(HttpClient);
  readonly selection = inject(CharacterSelectionService);

  readonly difficulties: Difficulty[] = ['normal', 'heroic', 'mythic'];
  readonly diffLabels: Record<Difficulty, string> = {
    normal: 'Normal', heroic: 'Heroic', mythic: 'Mythic',
  };

  readonly enchantOptions: { value: EnchantPolicy; label: string; info?: string }[] = [
    { value: 'none', label: 'Not required' },
    { value: 'any',  label: 'Any enchant on every enchantable item' },
    { value: 'top3', label: "Spec's meta enchants",
      info: "Every enchantable slot must have one of the most popular enchants for this character's spec, based on Archon.gg data." },
  ];
  readonly gemOptions: { value: GemPolicy; label: string; info?: string }[] = [
    { value: 'none',     label: 'Not required' },
    { value: 'any',      label: 'Any gem in each available socket' },
    { value: 'top_gems', label: "Spec's meta gems",
      info: "All sockets must be filled. At least one gem must be a top popular rare, and all remaining gems must be top popular epics for this spec, based on Archon.gg data." },
  ];
  readonly embellishOptions: { value: EmbellishPolicy; label: string; info?: string }[] = [
    { value: 'none', label: 'Not required' },
    { value: 'any',  label: 'Any 2 embellishments' },
    { value: 'top3', label: "Spec's meta embellishments",
      info: "The character must have 2 embellishments, both from the most popular embellishments for their spec, based on Archon.gg data." },
  ];

  readonly selectedDifficulty = signal<Difficulty>('mythic');
  readonly minIlvl = signal(275);
  readonly enchantPolicy = signal<EnchantPolicy>('none');
  readonly gemPolicy = signal<GemPolicy>('none');
  readonly embellishPolicy = signal<EmbellishPolicy>('none');

  readonly loading = signal(false);
  readonly hasRan = signal(false);
  readonly results = signal<MemberResult[]>([]);
  readonly checkedAt = signal<Date | null>(null);
  readonly panelChar = signal<PanelCharacter | null>(null);

  // Policies captured at run time — drive table columns so they don't shift on live changes
  readonly ranEnchantPolicy = signal<EnchantPolicy>('none');
  readonly ranGemPolicy = signal<GemPolicy>('none');
  readonly ranEmbellishPolicy = signal<EmbellishPolicy>('none');

  readonly guild = computed(() => {
    const c = this.selection.selected();
    return c?.guild_id != null ? c : null;
  });

  readonly canEdit = computed(() => {
    const c = this.selection.selected();
    return !!c && (c.is_gm || c.is_officer);
  });

  readonly passCount = computed(() =>
    this.results().filter(r =>
      r.ilvl.pass && r.enchants.pass && r.gems.pass && r.embellishments.pass
    ).length
  );

  constructor() {
    effect(() => {
      const g = this.guild();
      const diff = this.selectedDifficulty();
      if (g?.guild_id != null) {
        this._loadFromCache(g.guild_id, diff);
      } else {
        this.results.set([]);
        this.hasRan.set(false);
        this.checkedAt.set(null);
      }
    });
  }

  runCheck(): void {
    const char = this.guild();
    if (!char?.guild_id) return;
    this.loading.set(true);
    this.results.set([]);
    this.hasRan.set(true);
    this.ranEnchantPolicy.set(this.enchantPolicy());
    this.ranGemPolicy.set(this.gemPolicy());
    this.ranEmbellishPolicy.set(this.embellishPolicy());

    this.http.post<{ members: MemberResult[] }>('/api/v1/wow/roster-check', {
      guild_id: char.guild_id,
      difficulty: this.selectedDifficulty(),
      min_ilvl: this.minIlvl(),
      enchant_policy: this.enchantPolicy(),
      gem_policy: this.gemPolicy(),
      embellish_policy: this.embellishPolicy(),
    }).subscribe({
      next: ({ members }) => {
        this.results.set(members);
        this.loading.set(false);
        this.checkedAt.set(new Date());
        this._saveToCache(char.guild_id!);
      },
      error: () => this.loading.set(false),
    });
  }

  formatDate(d: Date): string {
    return d.toLocaleString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  }

  tooltip(r: CriterionResult): string {
    return r.failing.join(', ');
  }

  toRealmSlug(realm: string): string {
    return realm.toLowerCase().replace(/'/g, '').replace(/\s+/g, '-');
  }

  private _cacheKey(guildId: number, diff: Difficulty): string {
    return `roster-check:${guildId}:${diff}`;
  }

  private _saveToCache(guildId: number): void {
    const payload: CachedCheck = {
      results: this.results(),
      ranEnchantPolicy: this.ranEnchantPolicy(),
      ranGemPolicy: this.ranGemPolicy(),
      ranEmbellishPolicy: this.ranEmbellishPolicy(),
      minIlvl: this.minIlvl(),
      checkedAt: this.checkedAt()!.toISOString(),
    };
    localStorage.setItem(this._cacheKey(guildId, this.selectedDifficulty()), JSON.stringify(payload));
  }

  private _loadFromCache(guildId: number, diff: Difficulty): void {
    const raw = localStorage.getItem(this._cacheKey(guildId, diff));
    if (!raw) {
      this.results.set([]);
      this.hasRan.set(false);
      this.checkedAt.set(null);
      return;
    }
    try {
      const data: CachedCheck = JSON.parse(raw);
      this.results.set(data.results);
      this.ranEnchantPolicy.set(data.ranEnchantPolicy);
      this.ranGemPolicy.set(data.ranGemPolicy);
      this.ranEmbellishPolicy.set(data.ranEmbellishPolicy);
      this.minIlvl.set(data.minIlvl);
      this.hasRan.set(true);
      this.checkedAt.set(new Date(data.checkedAt));
    } catch {
      this.results.set([]);
      this.hasRan.set(false);
      this.checkedAt.set(null);
    }
  }
}
