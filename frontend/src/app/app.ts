import { Component, computed, inject, viewChild } from '@angular/core';
import { ChessBoardComponent } from './board/chess-board.component';
import { CoachStore } from './core/coach.store';
import { describeScore, formatScore, whiteShare } from './core/format';
import { GameStore } from './core/game.store';
import { CoachAdviceComponent } from './panel/coach-advice.component';
import { MoveListComponent } from './panel/move-list.component';
import { OpeningContextComponent } from './panel/opening-context.component';
import { SuggestionsComponent } from './panel/suggestions.component';
import { VideosComponent } from './panel/videos.component';

@Component({
  selector: 'app-root',
  imports: [ChessBoardComponent, MoveListComponent, SuggestionsComponent, CoachAdviceComponent, OpeningContextComponent, VideosComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss',
  host: {
    '(document:keydown.arrowleft)': 'onArrow($event, -1)',
    '(document:keydown.arrowright)': 'onArrow($event, 1)',
  },
})
export class App {
  protected readonly game = inject(GameStore);
  protected readonly coach = inject(CoachStore);
  private readonly board = viewChild.required(ChessBoardComponent);

  protected readonly evaluation = computed(() => {
    const s = this.coach.evaluation();
    return s.status === 'ok' ? s.data : null;
  });
  protected readonly formatScore = formatScore;
  protected readonly describeScore = describeScore;
  protected readonly whiteShare = whiteShare;

  protected onBoardMove(boardFen: string): void {
    if (!this.game.playFromBoardFen(boardFen)) {
      // coup refusé : on remet l'échiquier
      this.board().resync();
    }
  }

  protected onPlay(san: string): void {
    this.game.playSan(san);
  }

  protected onOpeningSelected(event: Event): void {
    const moves = (event.target as HTMLSelectElement).value;
    if (moves) this.game.loadLine(moves);
  }

  protected onArrow(event: Event, direction: -1 | 1): void {
    const target = event.target as HTMLElement | null;
    if (target?.closest('input, select, textarea')) return;
    if (direction < 0) this.game.previous();
    else this.game.next();
  }
}
