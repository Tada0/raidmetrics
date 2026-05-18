import { Component, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { RouterLink } from '@angular/router';
import { CharacterSelectionService } from '../../services/character-selection.service';

type Difficulty = 'normal' | 'heroic' | 'mythic';
type PruneStatus = 'ok' | 'expired' | 'gear_mismatch' | 'not_uploaded' | 'check_failed';

interface PruneResult {
  character_name: string;
  realm_slug: string;
  status: PruneStatus;
  details: string[];
}

@Component({
  selector: 'app-guild',
  imports: [RouterLink],
  templateUrl: './guild.component.html',
})
export class GuildComponent {
  private http = inject(HttpClient);
  readonly selection = inject(CharacterSelectionService);

  readonly difficulties: Difficulty[] = ['normal', 'heroic', 'mythic'];
  readonly diffLabels: Record<Difficulty, string> = { normal: 'Normal', heroic: 'Heroic', mythic: 'Mythic' };

  readonly pruneDifficulty = signal<Difficulty>('mythic');
  readonly pruneLoading = signal(false);
  readonly pruneResults = signal<PruneResult[] | null>(null);
  readonly pruneError = signal<string | null>(null);

  readonly isOfficer = computed(() => {
    const c = this.selection.selected();
    return c?.is_gm || c?.is_officer;
  });

  roleLabel(isGm: boolean, isOfficer: boolean): string {
    if (isGm) return 'Guild Master';
    if (isOfficer) return 'Officer';
    return 'Member';
  }

  selectPruneDifficulty(diff: Difficulty) {
    this.pruneDifficulty.set(diff);
    this.pruneResults.set(null);
    this.pruneError.set(null);
  }

  runPruneCheck() {
    const c = this.selection.selected();
    if (!c?.guild_id) return;

    this.pruneLoading.set(true);
    this.pruneResults.set(null);
    this.pruneError.set(null);

    this.http.post<{ difficulty: string; results: PruneResult[] }>(
      `/api/v1/wow/guilds/${c.guild_id}/loot/prune`,
      { difficulty: this.pruneDifficulty() }
    ).subscribe({
      next: ({ results }) => {
        this.pruneResults.set(results);
        this.pruneLoading.set(false);
      },
      error: (err) => {
        this.pruneError.set(err.error?.detail ?? 'Check failed. Please try again.');
        this.pruneLoading.set(false);
      },
    });
  }

  statusLabel(status: PruneStatus): string {
    return {
      ok: 'Report OK',
      expired: 'Expired — removed',
      gear_mismatch: 'Gear mismatch — removed',
      not_uploaded: 'Not uploaded',
      check_failed: 'Check failed',
    }[status];
  }

  statusClass(status: PruneStatus): string {
    return {
      ok: 'text-green-400',
      expired: 'text-amber-400',
      gear_mismatch: 'text-danger',
      not_uploaded: 'text-muted',
      check_failed: 'text-amber-400',
    }[status];
  }

  countByStatus(results: PruneResult[], status: PruneStatus): number {
    return results.filter(r => r.status === status).length;
  }
}
