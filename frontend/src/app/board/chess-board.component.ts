import { Component, DestroyRef, ElementRef, effect, inject, input, output, signal, viewChild } from '@angular/core';
import { MoveChange, NgxChessBoardComponent, NgxChessBoardModule } from 'ngx-chess-board';
import { samePosition } from '../core/game.store';

const MIN_SIZE = 260;
const MAX_SIZE = 640;

/**
 * Enveloppe de ngx-chess-board.
 * L'échiquier ne fait qu'afficher la position du GameStore et remonter les coups joués à la souris :
 * c'est le store (chess.js) qui décide si le coup est accepté.
 */
@Component({
  selector: 'app-chess-board',
  imports: [NgxChessBoardModule],
  template: `
    <ngx-chess-board
      #board
      [size]="size()"
      [showCoords]="true"
      [showLegalMoves]="true"
      [showLastMove]="true"
      [drawDisabled]="false"
      lightTileColor="#f0d9b5"
      darkTileColor="#b58863"
      (moveChange)="onMoveChange($event)"
    />
  `,
  styles: `
    :host {
      display: block;
      width: 100%;
    }
    ngx-chess-board {
      /* La librairie force inline-block : sans ça, un espace apparaît sous l'échiquier */
      vertical-align: top;
    }
  `,
})
export class ChessBoardComponent {
  readonly fen = input.required<string>();
  readonly orientation = input<'white' | 'black'>('white');
  /** FEN de l'échiquier après un coup joué à la souris */
  readonly moved = output<string>();

  protected readonly size = signal(480);
  private readonly board = viewChild.required<NgxChessBoardComponent>('board');
  /** Ce que ngx-chess-board affiche réellement (sa FEN interne n'est pas fiable après setFEN) */
  private shownFen = '';
  private reversed = false;

  constructor() {
    const host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
    const observer = new ResizeObserver(([entry]) => {
      const width = Math.floor(entry.contentRect.width);
      this.size.set(Math.max(MIN_SIZE, Math.min(MAX_SIZE, width)));
    });
    observer.observe(host);
    inject(DestroyRef).onDestroy(() => observer.disconnect());

    effect(() => {
      const fen = this.fen();
      const board = this.board();
      if (!samePosition(this.shownFen, fen)) {
        board.setFEN(fen);
        this.shownFen = fen;
      }
    });

    effect(() => {
      const reversed = this.orientation() === 'black';
      if (reversed !== this.reversed) {
        this.board().reverse();
        this.reversed = reversed;
      }
    });
  }

  protected onMoveChange(event: MoveChange): void {
    this.shownFen = event.fen;
    this.moved.emit(event.fen);
  }

  /** Remet l'échiquier sur la position du store (coup refusé par chess.js) */
  resync(): void {
    this.board().setFEN(this.fen());
    this.shownFen = this.fen();
  }
}
