import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';

export interface BisSpec {
  spec_slug: string;
  class_slug: string;
  spec_name: string;
  class_name: string;
}

export interface BisItem {
  slot: string;
  item_id: number;
  item_name: string;
  is_bis: boolean;
  usage_percent: number | null;
  gem_ids: string | null;
  enchant_id: number | null;
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
}

export interface PopularGem {
  gem_quality: 'epic' | 'rare';
  rank: number;
  item_id: number;
  gem_name: string;
  usage_percent: number | null;
}

export interface BisSnapshot {
  spec_slug: string;
  class_slug: string;
  scraped_at: string;
  bis_items: BisItem[];
  popular_items: PopularItem[];
  popular_enchants: PopularEnchant[];
  popular_gems: PopularGem[];
}

@Injectable({ providedIn: 'root' })
export class BisService {
  private http = inject(HttpClient);

  readonly specs = signal<BisSpec[] | null>(null);
  readonly snapshot = signal<BisSnapshot | null>(null);
  readonly loading = signal(false);

  loadSpecs(): void {
    this.http.get<BisSpec[]>('/api/v1/bis/specs').subscribe({
      next: s => this.specs.set(s),
      error: () => {},
    });
  }

  loadSnapshot(specSlug: string, classSlug: string): void {
    this.loading.set(true);
    this.snapshot.set(null);
    this.http.get<BisSnapshot>('/api/v1/bis/snapshot', {
      params: { spec: specSlug, class: classSlug },
    }).subscribe({
      next: s => {
        this.snapshot.set(s);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }
}
