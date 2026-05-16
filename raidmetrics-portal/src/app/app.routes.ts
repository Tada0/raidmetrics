import { Routes } from '@angular/router';
import { LoginComponent } from './pages/login/login.component';
import { CallbackComponent } from './pages/callback/callback.component';
import { DashboardComponent } from './pages/dashboard/dashboard.component';
import { CharacterDetailComponent } from './pages/character-detail/character-detail.component';
import { GuildComponent } from './pages/guild/guild.component';
import { RaidRosterComponent } from './pages/raid-roster/raid-roster.component';
import { BisViewerComponent } from './pages/bis-viewer/bis-viewer.component';
import { RaidRosterCheckComponent } from './pages/raid-roster-check/raid-roster-check.component';
import { DashboardLayoutComponent } from './layouts/dashboard-layout/dashboard-layout.component';
import { authGuard } from './guards/auth.guard';

export const routes: Routes = [
  { path: '', component: LoginComponent },
  { path: 'auth/battlenet/callback', component: CallbackComponent },
  {
    path: 'dashboard',
    component: DashboardLayoutComponent,
    canActivate: [authGuard],
    children: [
      { path: '', component: DashboardComponent },
      { path: 'character', component: CharacterDetailComponent },
      { path: 'guild', component: GuildComponent },
      { path: 'raid-roster', component: RaidRosterComponent },
      { path: 'raid-roster-check', component: RaidRosterCheckComponent },
      { path: 'bis', component: BisViewerComponent },
    ],
  },
];
