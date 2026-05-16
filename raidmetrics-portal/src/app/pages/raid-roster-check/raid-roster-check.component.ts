import { Component, computed, inject } from '@angular/core';
import { CharacterSelectionService } from '../../services/character-selection.service';

@Component({
  selector: 'app-raid-roster-check',
  templateUrl: './raid-roster-check.component.html',
})
export class RaidRosterCheckComponent {
  readonly selection = inject(CharacterSelectionService);
  readonly char = computed(() => this.selection.selected());
}
