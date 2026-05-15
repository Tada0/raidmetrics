import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CharacterSelectionService } from '../../services/character-selection.service';

@Component({
  selector: 'app-guild',
  imports: [RouterLink],
  templateUrl: './guild.component.html',
})
export class GuildComponent {
  readonly selection = inject(CharacterSelectionService);

  roleLabel(isGm: boolean, isOfficer: boolean): string {
    if (isGm) return 'Guild Master';
    if (isOfficer) return 'Officer';
    return 'Member';
  }
}
