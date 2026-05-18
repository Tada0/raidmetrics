import { Component, computed, effect, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { DatePipe, DecimalPipe } from '@angular/common';
import { CharacterSelectionService } from '../../services/character-selection.service';

type Difficulty = 'normal' | 'heroic' | 'mythic';

interface LootReportMeta {
  id: number;
  character_name: string;
  realm_slug: string;
  difficulty: string;
  raidbots_report_id: string;
  baseline_dps: number;
  updated_at: string;
}

interface LootItem {
  zone_id: number;
  encounter_id: number;
  item_id: number;
  item_ilvl: number;
  slot_name: string;
  item_name: string | null;
  boss_name: string | null;
  raid_name: string | null;
  upgrade_dps: number;
  upgrade_pct: number;
}

interface BossGroup {
  boss_name: string;
  raid_name: string;
  encounter_id: number;
  best_pct: number;
  items: LootItem[];
}

@Component({
  selector: 'app-loot',
  imports: [FormsModule, DatePipe, DecimalPipe],
  templateUrl: './loot.component.html',
})
export class LootComponent {
  private http = inject(HttpClient);
  readonly selection = inject(CharacterSelectionService);

  readonly difficulties: Difficulty[] = ['normal', 'heroic', 'mythic'];
  readonly diffLabels: Record<Difficulty, string> = {
    normal: 'Normal', heroic: 'Heroic', mythic: 'Mythic',
  };

  readonly selectedDifficulty = signal<Difficulty>('mythic');

  readonly icons = signal<Map<number, string>>(new Map());
  readonly report = signal<LootReportMeta | null>(null);
  readonly bossGroups = signal<BossGroup[]>([]);
  readonly loading = signal(false);
  readonly uploading = signal(false);
  readonly showUpload = signal(false);
  readonly reportUrl = signal('');
  readonly uploadError = signal<string | string[] | null>(null);

  readonly errorLines = computed<string[]>(() => {
    const e = this.uploadError();
    if (!e) return [];
    return Array.isArray(e) ? e : [e];
  });

  readonly char = computed(() => {
    const c = this.selection.selected();
    return c?.guild_id != null ? c : null;
  });

  constructor() {
    effect(() => {
      const c = this.char();
      const diff = this.selectedDifficulty();
      if (c) {
        this._loadReport(c.guild_id!, c.name, c.realm_slug, diff);
      } else {
        this.report.set(null);
        this.bossGroups.set([]);
      }
    });
  }

  private _loadReport(guildId: number, characterName: string, realmSlug: string, difficulty: string) {
    this.loading.set(true);
    this.report.set(null);
    this.bossGroups.set([]);
    this.icons.set(new Map());
    this.showUpload.set(false);
    this.uploadError.set(null);

    this.http.get<{ report: LootReportMeta | null; items: LootItem[] }>(
      `/api/v1/wow/guilds/${guildId}/loot`,
      { params: { character_name: characterName, realm_slug: realmSlug, difficulty } }
    ).subscribe({
      next: ({ report, items }) => {
        this.report.set(report);
        if (report) {
          const groups = this._groupByBoss(items);
          this.bossGroups.set(groups);
          this._loadIcons(items.map(i => i.item_id));
        }
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
      },
    });
  }

  private _loadIcons(itemIds: number[]) {
    const unique = [...new Set(itemIds)];
    if (!unique.length) return;
    this.http.get<Record<string, string>>('/api/v1/bis/item-icons', {
      params: { ids: unique.join(',') },
    }).subscribe({
      next: map => {
        const m = new Map<number, string>();
        for (const [id, url] of Object.entries(map)) {
          if (url) m.set(Number(id), url);
        }
        this.icons.set(m);
      },
      error: () => {},
    });
  }

  private _groupByBoss(items: LootItem[]): BossGroup[] {
    const map = new Map<number, BossGroup>();
    for (const item of items) {
      if (!map.has(item.encounter_id)) {
        map.set(item.encounter_id, {
          boss_name: item.boss_name ?? `Boss ${item.encounter_id}`,
          raid_name: item.raid_name ?? '',
          encounter_id: item.encounter_id,
          best_pct: 0,
          items: [],
        });
      }
      const group = map.get(item.encounter_id)!;
      group.items.push(item);
      if (item.upgrade_pct > group.best_pct) group.best_pct = item.upgrade_pct;
    }

    for (const group of map.values()) {
      group.items.sort((a, b) => b.upgrade_pct - a.upgrade_pct);
    }

    return Array.from(map.values()).sort((a, b) => b.best_pct - a.best_pct);
  }

  selectDifficulty(diff: Difficulty) {
    this.selectedDifficulty.set(diff);
    this.showUpload.set(false);
    this.reportUrl.set('');
    this.uploadError.set(null);
  }

  openUpload() {
    this.showUpload.set(true);
    this.reportUrl.set('');
    this.uploadError.set(null);
  }

  cancelUpload() {
    this.showUpload.set(false);
    this.uploadError.set(null);
  }

  submitReport() {
    const c = this.char();
    if (!c?.guild_id || !this.reportUrl().trim()) return;

    const realmSlug = c.realm_slug;

    this.uploading.set(true);
    this.uploadError.set(null);

    this.http.post<{ report: LootReportMeta; items: LootItem[] }>(
      `/api/v1/wow/guilds/${c.guild_id}/loot/report`,
      {
        report_url: this.reportUrl().trim(),
        difficulty: this.selectedDifficulty(),
        character_name: c.name,
        realm_slug: c.realm_slug,
      }
    ).subscribe({
      next: ({ report, items }) => {
        this.report.set(report);
        this.bossGroups.set(this._groupByBoss(items));
        this._loadIcons(items.map(i => i.item_id));
        this.uploading.set(false);
        this.showUpload.set(false);
        this.reportUrl.set('');
      },
      error: (err) => {
        const detail = err.error?.detail;
        this.uploadError.set(Array.isArray(detail) ? detail : (detail ?? 'Upload failed. Please try again.'));
        this.uploading.set(false);
      },
    });
  }

  formatPct(pct: number): string {
    return (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
  }

  formatDps(dps: number): string {
    return (dps >= 0 ? '+' : '') + Math.round(dps).toLocaleString();
  }

  slotLabel(slot: string): string {
    return slot.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  iconUrl(itemId: number): string | null {
    return this.icons().get(itemId) ?? null;
  }

  wowheadHref(itemId: number, ilvl: number): string {
    return `https://www.wowhead.com/item=${itemId}?ilvl=${ilvl}`;
  }

  wowheadData(itemId: number, ilvl: number): string {
    return `item=${itemId}&ilvl=${ilvl}`;
  }
}
