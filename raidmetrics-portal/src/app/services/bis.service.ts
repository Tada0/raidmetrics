import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';

export interface BisSpec {
  spec_slug: string;
  class_slug: string;
  spec_name: string;
  class_name: string;
}

export interface PopularItem {
  slot: string;
  rank: number;
  item_id: number;
  item_name: string;
  usage_percent: number | null;
  is_crafted: boolean;
  is_embellishment: boolean;
}

export interface PopularEnchant {
  slot: string;
  rank: number;
  enchant_id: number;
  enchant_name: string;
  usage_percent: number | null;
  icon_name: string;
}

export interface PopularGem {
  gem_quality: 'epic' | 'rare';
  rank: number;
  item_id: number;
  gem_name: string;
  usage_percent: number | null;
}

export interface WowheadBisItem {
  slot: string;
  item_id: number;
  item_name: string;
}

export interface BisSnapshot {
  spec_slug: string;
  class_slug: string;
  scraped_at: string;
  popular_items: PopularItem[];
  popular_enchants: PopularEnchant[];
  popular_gems: PopularGem[];
  wowhead_bis_items: WowheadBisItem[];
}

@Injectable({ providedIn: 'root' })
export class BisService {
  private http = inject(HttpClient);

  readonly specs = signal<BisSpec[] | null>(null);
  readonly snapshot = signal<BisSnapshot | null>(null);
  readonly icons = signal<Map<number, string>>(new Map());
  readonly loading = signal(false);
  readonly selectedClass = signal<string | null>(null);
  readonly selectedSpec = signal<string | null>(null);

  loadSpecs(): void {
    this.http.get<BisSpec[]>('/api/v1/bis/specs').subscribe({
      next: s => this.specs.set(s),
      error: () => {},
    });
  }

  loadSnapshot(specSlug: string, classSlug: string): void {
    this.loading.set(true);
    this.snapshot.set(null);
    this.icons.set(new Map());
    this.http.get<BisSnapshot>('/api/v1/bis/snapshot', {
      params: { spec: specSlug, class: classSlug },
    }).subscribe({
      next: s => {
        this.snapshot.set(s);
        this.loading.set(false);
        const ids = [...new Set([
          ...s.popular_items.map(i => i.item_id),
          ...s.popular_gems.map(g => g.item_id),
          ...s.wowhead_bis_items.map(i => i.item_id),
        ])];
        if (ids.length) this._loadIcons(ids);
      },
      error: () => this.loading.set(false),
    });
  }

  private _loadIcons(itemIds: number[]): void {
    this.http.get<Record<string, string>>('/api/v1/bis/item-icons', {
      params: { ids: itemIds.join(',') },
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
}
