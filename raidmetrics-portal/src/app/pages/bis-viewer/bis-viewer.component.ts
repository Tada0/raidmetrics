import { Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import {
  BisService,
  BisSpec,
  PopularEnchant,
  PopularGem,
  PopularItem,
  WowheadBisItem,
} from '../../services/bis.service';

type Tab = 'bis' | 'gear' | 'crafted' | 'enchants' | 'gems';

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
    { id: 'crafted', label: 'Crafted Gear' },
    { id: 'enchants', label: 'Enchants' },
    { id: 'gems', label: 'Gems' },
  ];

  private readonly SPEC_ICONS: Record<string, string> = {
    'blood/death-knight':     'spell_deathknight_bloodpresence',
    'frost/death-knight':     'spell_deathknight_frostpresence',
    'unholy/death-knight':    'spell_deathknight_unholypresence',
    'devourer/demon-hunter':  'ability_demonhunter_specdevourer',
    'havoc/demon-hunter':     'ability_demonhunter_specdps',
    'vengeance/demon-hunter': 'ability_demonhunter_spectank',
    'balance/druid':          'spell_nature_starfall',
    'feral/druid':            'ability_druid_catform',
    'guardian/druid':         'ability_racial_bearform',
    'restoration/druid':      'spell_nature_healingtouch',
    'augmentation/evoker':    'classicon_evoker_augmentation',
    'devastation/evoker':     'classicon_evoker_devastation',
    'preservation/evoker':    'classicon_evoker_preservation',
    'beast-mastery/hunter':   'ability_hunter_bestialdiscipline',
    'marksmanship/hunter':    'ability_hunter_focusedaim',
    'survival/hunter':        'ability_hunter_camouflage',
    'arcane/mage':            'spell_holy_magicalsentry',
    'fire/mage':              'spell_fire_firebolt02',
    'frost/mage':             'spell_frost_frostbolt02',
    'brewmaster/monk':        'spell_monk_brewmaster_spec',
    'mistweaver/monk':        'spell_monk_mistweaver_spec',
    'windwalker/monk':        'spell_monk_windwalker_spec',
    'holy/paladin':           'spell_holy_holybolt',
    'protection/paladin':     'ability_paladin_shieldofthetemplar',
    'retribution/paladin':    'spell_holy_auraoflight',
    'discipline/priest':      'spell_holy_powerwordshield',
    'holy/priest':            'spell_holy_guardianspirit',
    'shadow/priest':          'spell_shadow_shadowform',
    'assassination/rogue':    'ability_rogue_deadlybrew',
    'outlaw/rogue':           'ability_rogue_waylay',
    'subtlety/rogue':         'ability_stealth',
    'elemental/shaman':       'spell_nature_lightning',
    'enhancement/shaman':     'spell_shaman_improvedstormstrike',
    'restoration/shaman':     'spell_nature_magicimmunity',
    'affliction/warlock':     'spell_shadow_deathcoil',
    'demonology/warlock':     'spell_shadow_metamorphosis',
    'destruction/warlock':    'spell_shadow_rainoffire',
    'arms/warrior':           'ability_warrior_savageblow',
    'fury/warrior':           'ability_warrior_innerrage',
    'protection/warrior':     'ability_warrior_defensivestance',
  };

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
    'head', 'neck', 'shoulder', 'shoulders', 'back',
    'chest', 'wrist', 'wrists', 'hands', 'waist', 'legs', 'feet',
    'ring', 'trinket',
    'main-hand', 'off-hand', 'ranged', 'two-hand',
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

  private readonly WEAPON_SLOTS = new Set(['two-hand', 'main-hand', 'off-hand', 'ranged']);

  readonly bisItems = computed((): WowheadBisItem[] => {
    const snap = this.bis.snapshot();
    if (!snap) return [];
    return this._sortBySlot(snap.wowhead_bis_items, i => i.slot);
  });

  readonly bisItemIds = computed((): Set<number> => {
    const snap = this.bis.snapshot();
    return snap ? new Set(snap.wowhead_bis_items.map(i => i.item_id)) : new Set();
  });

  readonly bisArmorItems = computed(() =>
    this.bisItems().filter(i => !this.WEAPON_SLOTS.has(i.slot) && i.slot !== 'ring' && i.slot !== 'trinket')
  );

  readonly bisRingItems = computed(() =>
    this.bisItems().filter(i => i.slot === 'ring')
  );

  readonly bisTrinketItems = computed(() =>
    this.bisItems().filter(i => i.slot === 'trinket')
  );

  readonly bisWeaponItems = computed(() =>
    this.bisItems().filter(i => this.WEAPON_SLOTS.has(i.slot))
  );

  readonly hasMultipleWeaponTypes = computed(() => {
    const weapons = this.bisWeaponItems();
    const has2H = weapons.some(i => i.slot === 'two-hand');
    const has1H = weapons.some(i => i.slot === 'main-hand' || i.slot === 'off-hand');
    return has2H && has1H;
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
    this.bis.snapshot()?.popular_items.filter(i => i.is_crafted && !i.is_embellishment) ?? []
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

  classIconUrl(classSlug: string): string {
    return `https://wow.zamimg.com/images/wow/icons/medium/classicon_${classSlug.replace(/-/g, '')}.jpg`;
  }

  specIconUrl(spec: BisSpec): string | null {
    const key = `${spec.spec_slug}/${spec.class_slug}`;
    const icon = this.SPEC_ICONS[key];
    return icon ? `/icons/specs/${icon}.jpg` : null;
  }

  wowheadItem(itemId: number): string {
    return `https://www.wowhead.com/item=${itemId}`;
  }

  iconUrl(itemId: number): string | null {
    return this.bis.icons().get(itemId) ?? null;
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
