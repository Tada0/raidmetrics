import { Component, computed, effect, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CharacterSelectionService } from '../../services/character-selection.service';
import { CharacterDetail, CharacterItem, WowService } from '../../services/wow.service';

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
  POOR: '#9d9d9d',
  COMMON: '#ffffff',
  UNCOMMON: '#1eff00',
  RARE: '#0070dd',
  EPIC: '#a335ee',
  LEGENDARY: '#ff8000',
  ARTIFACT: '#e6cc80',
  HEIRLOOM: '#00ccff',
};

@Component({
  selector: 'app-character-detail',
  imports: [RouterLink],
  templateUrl: './character-detail.component.html',
})
export class CharacterDetailComponent {
  readonly selection = inject(CharacterSelectionService);
  private wow = inject(WowService);

  readonly char = computed(() => this.selection.selected());
  readonly detail = signal<CharacterDetail | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  readonly slotLabels = SLOT_LABELS;

  readonly leftItems = computed(() => this._slotItems(LEFT_SLOTS));
  readonly rightItems = computed(() => this._slotItems(RIGHT_SLOTS));
  readonly weaponItems = computed(() => {
    const map = this._itemMap();
    return WEAPON_SLOTS.map(s => map.get(s)).filter((i): i is CharacterItem => !!i);
  });

  constructor() {
    effect(() => {
      const char = this.char();
      if (char?.realm_slug) {
        this._load(char.realm_slug, char.name);
      } else {
        this.detail.set(null);
      }
    });
  }

  private _load(realmSlug: string, characterName: string): void {
    this.loading.set(true);
    this.error.set(null);
    this.wow.getCharacterDetail(realmSlug, characterName).subscribe({
      next: data => { this.detail.set(data); this.loading.set(false); },
      error: () => { this.error.set('Failed to load character data.'); this.loading.set(false); },
    });
  }

  private _itemMap(): Map<string, CharacterItem> {
    return new Map((this.detail()?.items ?? []).map(i => [i.slot_type, i]));
  }

  private _slotItems(slots: string[]): (CharacterItem | null)[] {
    const map = this._itemMap();
    return slots.map(s => map.get(s) ?? null);
  }

  qualityColor(quality: string): string {
    return QUALITY_COLORS[quality] ?? '#cdd5e0';
  }

  slotLabel(slotType: string): string {
    return SLOT_LABELS[slotType] ?? slotType;
  }
}
