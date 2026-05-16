import { Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import {
  BisService,
  BisSpec,
  BisItem,
  PopularItem,
  PopularEnchant,
  PopularGem,
} from '../../services/bis.service';

type Tab = 'bis' | 'gear' | 'enchants' | 'gems';

@Component({
  selector: 'app-bis-viewer',
  imports: [DatePipe],
  templateUrl: './bis-viewer.component.html',
})
export class BisViewerComponent {
  readonly bis = inject(BisService);

  readonly selectedClass = signal<string | null>(null);
  readonly selectedSpec = signal<string | null>(null);
  readonly activeTab = signal<Tab>('bis');

  readonly tabs: { id: Tab; label: string }[] = [
    { id: 'bis', label: 'BiS Gear' },
    { id: 'gear', label: 'Popular Gear' },
    { id: 'enchants', label: 'Enchants' },
    { id: 'gems', label: 'Gems' },
  ];

  private readonly CLASS_COLORS: Record<string, string> = {
    'death-knight': '#C41E3A',
    'demon-hunter': '#A330C9',
    'druid':        '#FF7C0A',
    'evoker':       '#33937F',
    'hunter':       '#AAD372',
    'mage':         '#3FC7EB',
    'monk':         '#00FF98',
    'paladin':      '#F48CBA',
    'priest':       '#FFFFFF',
    'rogue':        '#FFF468',
    'shaman':       '#0070DD',
    'warlock':      '#8788EE',
    'warrior':      '#C69B3A',
  };

  private readonly SLOT_ORDER = [
    'head', 'neck', 'shoulder', 'shoulders', 'back', 'cloak',
    'chest', 'wrist', 'wrists', 'hands', 'waist', 'legs', 'feet',
    'ring 1', 'ring 2', 'finger 1', 'finger 2',
    'trinket 1', 'trinket 2',
    'main hand', 'main-hand', 'off hand', 'off-hand',
    'ranged', 'two-hand', 'two hand',
  ];

  readonly classes = computed(() => {
    const specs = this.bis.specs();
    if (!specs) return [];
    const seen = new Set<string>();
    const result: { class_slug: string; class_name: string }[] = [];
    for (const s of specs) {
      if (!seen.has(s.class_slug)) {
        seen.add(s.class_slug);
        result.push({ class_slug: s.class_slug, class_name: s.class_name });
      }
    }
    return result;
  });

  readonly specsForClass = computed(() => {
    const specs = this.bis.specs();
    const cls = this.selectedClass();
    if (!specs || !cls) return [];
    return specs.filter(s => s.class_slug === cls);
  });

  readonly bisItems = computed((): BisItem[] => {
    const snap = this.bis.snapshot();
    if (!snap) return [];
    return this._sortBySlot(snap.bis_items, i => i.slot);
  });

  readonly popularBySlot = computed((): [string, PopularItem[]][] => {
    const snap = this.bis.snapshot();
    if (!snap) return [];
    return this._groupBySlot(
      snap.popular_items.filter(i => !i.is_crafted && !i.is_embellishment),
      i => i.slot,
    );
  });

  readonly craftedItems = computed((): PopularItem[] =>
    this.bis.snapshot()?.popular_items.filter(i => i.is_crafted) ?? []
  );

  readonly embellishments = computed((): PopularItem[] =>
    this.bis.snapshot()?.popular_items.filter(i => i.is_embellishment) ?? []
  );

  readonly enchantsBySlot = computed((): [string, PopularEnchant[]][] => {
    const snap = this.bis.snapshot();
    if (!snap) return [];
    return this._groupBySlot(snap.popular_enchants, e => e.slot);
  });

  readonly epicGems = computed((): PopularGem[] =>
    this.bis.snapshot()?.popular_gems.filter(g => g.gem_quality === 'epic') ?? []
  );

  readonly rareGems = computed((): PopularGem[] =>
    this.bis.snapshot()?.popular_gems.filter(g => g.gem_quality === 'rare') ?? []
  );

  constructor() {
    this.bis.loadSpecs();
  }

  selectClass(classSlug: string): void {
    if (this.selectedClass() === classSlug) return;
    this.selectedClass.set(classSlug);
    this.selectedSpec.set(null);
    this.bis.snapshot.set(null);
  }

  selectSpec(spec: BisSpec): void {
    this.selectedSpec.set(spec.spec_slug);
    this.activeTab.set('bis');
    this.bis.loadSnapshot(spec.spec_slug, spec.class_slug);
  }

  classColor(classSlug: string): string {
    return this.CLASS_COLORS[classSlug] ?? '#CCCCCC';
  }

  wowheadItem(itemId: number): string {
    return `https://www.wowhead.com/item=${itemId}`;
  }

  private _slotRank(slot: string): number {
    const idx = this.SLOT_ORDER.indexOf(slot.toLowerCase());
    return idx === -1 ? 999 : idx;
  }

  private _sortBySlot<T>(items: T[], getSlot: (i: T) => string): T[] {
    return [...items].sort((a, b) => {
      const diff = this._slotRank(getSlot(a)) - this._slotRank(getSlot(b));
      return diff !== 0 ? diff : getSlot(a).localeCompare(getSlot(b));
    });
  }

  private _groupBySlot<T>(items: T[], getSlot: (i: T) => string): [string, T[]][] {
    const map = new Map<string, T[]>();
    for (const item of items) {
      const slot = getSlot(item);
      if (!map.has(slot)) map.set(slot, []);
      map.get(slot)!.push(item);
    }
    return [...map.entries()].sort(([a], [b]) => {
      const diff = this._slotRank(a) - this._slotRank(b);
      return diff !== 0 ? diff : a.localeCompare(b);
    });
  }
}
