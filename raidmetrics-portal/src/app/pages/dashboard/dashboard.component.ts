import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { catchError, map, of, startWith } from 'rxjs';
import { WowService, WowCharacter } from '../../services/wow.service';

interface DashboardState {
  loading: boolean;
  characters: WowCharacter[];
  error: string;
}

const LOADING: DashboardState = { loading: true, characters: [], error: '' };

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent {
  private wow = inject(WowService);

  state = toSignal(
    this.wow.getCharacters().pipe(
      map(({ characters }): DashboardState => ({ loading: false, characters, error: '' })),
      catchError(() => of<DashboardState>({ loading: false, characters: [], error: 'Failed to load characters.' })),
      startWith(LOADING),
    ),
    { initialValue: LOADING }
  );
}
