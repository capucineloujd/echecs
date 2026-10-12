import { Component, computed, input, output } from '@angular/core';
import { MovesResponse } from '../core/api.models';
import { compactNumber, describeScore, formatScore } from '../core/format';
import { LoadState } from '../core/load-state';

/** Coups suggérés : théorie Lichess, ou lignes Stockfish une fois sorti de la théorie */
@Component({
  selector: 'app-suggestions',
  template: `
    <section class="card" aria-labelledby="suggestions-title" [attr.aria-busy]="state().status === 'loading'">
      <h2 id="suggestions-title">Coups suggérés</h2>

      @switch (state().status) {
        @case ('loading') {
          <ul class="skeleton" aria-label="Chargement des coups">
            <li></li>
            <li></li>
            <li></li>
          </ul>
        }
        @case ('error') {
          <div class="error" role="alert">
            <p>{{ errorMessage() }}</p>
            <button type="button" (click)="retry.emit()">Réessayer</button>
          </div>
        }
        @case ('ok') {
          @let data = response()!;
          @if (gameOver()) {
            <p class="muted">{{ gameOver() }} : la partie est terminée.</p>
          } @else if (data.in_theory) {
            <p class="hint">
              Coups joués par les {{ data.database === 'masters' ? 'maîtres' : 'joueurs Lichess' }}
              dans cette position ({{ total(data.total_games) }} parties). Clique sur un coup pour le jouer.
            </p>
            <ol class="moves">
              @for (move of data.moves; track move.uci; let first = $first) {
                <li>
                  <button type="button" class="move" [class.top]="first" (click)="play.emit(move.san)"
                          [attr.aria-label]="'Jouer ' + move.san">
                    <span class="san">{{ move.san }}</span>
                    <span class="games">{{ share(move.games, data.total_games) }} %</span>
                    <span class="bar" [attr.title]="'Blancs ' + move.white_pct + ' % · Nulles ' + move.draw_pct + ' % · Noirs ' + move.black_pct + ' %'">
                      <span class="w" [style.width.%]="move.white_pct">{{ move.white_pct >= 15 ? move.white_pct + '%' : '' }}</span>
                      <span class="d" [style.width.%]="move.draw_pct">{{ move.draw_pct >= 15 ? move.draw_pct + '%' : '' }}</span>
                      <span class="b" [style.width.%]="move.black_pct">{{ move.black_pct >= 15 ? move.black_pct + '%' : '' }}</span>
                    </span>
                  </button>
                </li>
              }
            </ol>
          } @else if (data.engine; as engine) {
            <p class="hint">
              <strong>Tu es sorti de la théorie.</strong> Voici ce que propose Stockfish
              ({{ describe(engine) }}).
            </p>
            <ol class="moves">
              @for (line of engine.lines; track line.rank; let first = $first) {
                <li>
                  <button type="button" class="move engine" [class.top]="first" (click)="play.emit(line.pv_san[0])"
                          [attr.aria-label]="'Jouer ' + line.pv_san[0]">
                    <span class="san">{{ line.pv_san[0] }}</span>
                    <span class="score">{{ score(line.score) }}</span>
                    <span class="pv">{{ line.pv_san.slice(1, 6).join(' ') }}</span>
                  </button>
                </li>
              }
            </ol>
          }
          @if (data.warning) {
            <p class="warning">{{ data.warning }}</p>
          }
        }
      }
    </section>
  `,
  styleUrl: './panel.scss',
})
export class SuggestionsComponent {
  readonly state = input.required<LoadState<MovesResponse>>();
  readonly gameOver = input<string | null>(null);
  readonly play = output<string>();
  readonly retry = output<void>();

  protected readonly response = computed(() => {
    const s = this.state();
    return s.status === 'ok' ? s.data : null;
  });

  protected readonly errorMessage = computed(() => {
    const s = this.state();
    if (s.status !== 'error') return '';
    const wait = s.error.retryAfter ? ` Réessaie dans ${s.error.retryAfter} s.` : '';
    return `Impossible de récupérer les coups : ${s.error.message}${wait}`;
  });

  protected total = compactNumber;
  protected score = formatScore;

  protected share(games: number, total: number): number {
    return total ? Math.round((100 * games) / total) : 0;
  }

  protected describe(engine: NonNullable<MovesResponse['engine']>): string {
    return describeScore(engine.score).toLowerCase();
  }
}
