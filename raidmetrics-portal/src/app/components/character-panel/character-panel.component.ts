import { DecimalPipe } from '@angular/common';
import { Component, computed, effect, inject, input, output, signal } from '@angular/core';
import { BisService } from '../../services/bis.service';
import { CharacterDetail, CharacterGearCheck, CharacterItem, GearStatus, WowService } from '../../services/wow.service';

const LEFT_SLOTS  = ['HEAD', 'NECK', 'SHOULDER', 'BACK', 'CHEST', 'SHIRT', 'TABARD', 'WRIST'];
const RIGHT_SLOTS = ['HANDS', 'WAIST', 'LEGS', 'FEET', 'FINGER_1', 'FINGER_2', 'TRINKET_1', 'TRINKET_2'];
const WEAPON_SLOTS = ['MAIN_HAND', 'OFF_HAND', 'TWOHANDED', 'RANGED'];

const SLOT_LABELS: Record<string, string> = {
  HEAD: 'Head', NECK: 'Neck', SHOULDER: 'Shoulders', BACK: 'Back',
  CHEST: 'Chest', SHIRT: 'Shirt', TABARD: 'Tabard', WRIST: 'Wrist',
  HANDS: 'Hands', WAIST: 'Waist', LEGS: 'Legs', FEET: 'Feet',
  FINGER_1: 'Ring 1', FINGER_2: 'Ring 2', TRINKET_1: 'Trinket 1', TRINKET_2: 'Trinket 2',
  MAIN_HAND: 'Main Hand', OFF_HAND: 'Off Hand', TWOHANDED: 'Two-Hand', RANGED: 'Ranged',
};

const QUALITY_COLORS: Record<string, string> = {
  POOR: '#9d9d9d', COMMON: '#ffffff', UNCOMMON: '#1eff00', RARE: '#0070dd',
  EPIC: '#a335ee', LEGENDARY: '#ff8000', ARTIFACT: '#e6cc80', HEIRLOOM: '#00ccff',
};

export interface PanelCharacter {
  realm_slug: string;
  name: string;
}

@Component({
  selector: 'app-character-panel',
  imports: [DecimalPipe],
  templateUrl: './character-panel.component.html',
})
export class CharacterPanelComponent {
  readonly character = input<PanelCharacter | null>(null);
  readonly closed = output<void>();

  private wow = inject(WowService);
  readonly bis = inject(BisService);

  readonly detail = signal<CharacterDetail | null>(null);
  readonly gearCheck = signal<CharacterGearCheck | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  readonly bisItemIds = computed(() =>
    new Set(this.bis.snapshot()?.wowhead_bis_items.map(i => i.item_id) ?? [])
  );

  readonly leftItems  = computed(() => this._slotItems(LEFT_SLOTS));
  readonly rightItems = computed(() => this._slotItems(RIGHT_SLOTS));
  readonly weaponItems = computed(() => {
    const map = this._itemMap();
    return WEAPON_SLOTS.map(s => map.get(s)).filter((i): i is CharacterItem => !!i);
  });
  readonly primaryStat = computed(() => {
    const s = this.detail()?.stats;
    if (!s) return null;
    return [
      { name: 'Strength', value: s.strength },
      { name: 'Agility',  value: s.agility },
      { name: 'Intellect', value: s.intellect },
    ].reduce((a, b) => a.value >= b.value ? a : b);
  });

  constructor() {
    this.bis.loadSpecs();

    effect(() => {
      const char = this.character();
      if (char) {
        this._load(char.realm_slug, char.name);
      } else {
        this.detail.set(null);
        this.gearCheck.set(null);
        this.error.set(null);
      }
    });

    effect(() => {
      const d = this.detail();
      const specs = this.bis.specs();
      if (!d?.spec || !specs) return;
      const spec = specs.find(s => s.spec_name === d.spec && s.class_name === d.class);
      if (spec) this.bis.loadSnapshot(spec.spec_slug, spec.class_slug);
    });
  }

  private _load(realmSlug: string, characterName: string): void {
    this.loading.set(true);
    this.error.set(null);
    this.gearCheck.set(null);
    this.wow.getCharacterDetail(realmSlug, characterName).subscribe({
      next: data => { this.detail.set(data); this.loading.set(false); },
      error: () => { this.error.set('Failed to load character data.'); this.loading.set(false); },
    });
    this.wow.getCharacterGearCheck(realmSlug, characterName).subscribe({
      next: data => this.gearCheck.set(data),
      error: () => {},
    });
  }

  statusIcon(status: GearStatus): string {
    return status === 'green' ? '✓' : status === 'yellow' ? '⚠' : '✗';
  }

  statusClass(status: GearStatus): string {
    return status === 'green'  ? 'text-green-400' :
           status === 'yellow' ? 'text-yellow-400' : 'text-danger';
  }

  qualityColor(quality: string): string { return QUALITY_COLORS[quality] ?? '#cdd5e0'; }
  slotLabel(slotType: string): string   { return SLOT_LABELS[slotType] ?? slotType; }

  wowheadHref(item: CharacterItem): string {
    return `https://www.wowhead.com/item=${item.item_id}?${this._wowheadParams(item)}`;
  }
  wowheadData(item: CharacterItem): string {
    return `item=${item.item_id}&${this._wowheadParams(item)}`;
  }

  private _wowheadParams(item: CharacterItem): string {
    let s = `ilvl=${item.item_level}`;
    if (item.bonus_ids?.length)     s += `&bonus=${item.bonus_ids.join(':')}`;
    if (item.enchantment_id)        s += `&ench=${item.enchantment_id}`;
    if (item.gem_ids?.length)       s += `&gems=${item.gem_ids.join(':')}`;
    if (item.crafted_stats?.length) s += `&crafted_stats=${item.crafted_stats.join(':')}`;
    return s;
  }

  private _itemMap(): Map<string, CharacterItem> {
    return new Map((this.detail()?.items ?? []).map(i => [i.slot_type, i]));
  }

  private _slotItems(slots: string[]): (CharacterItem | null)[] {
    const map = this._itemMap();
    return slots.map(s => map.get(s) ?? null);
  }
}
