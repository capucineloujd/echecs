import { Injectable, computed, signal } from '@angular/core';
import { Chess, DEFAULT_POSITION, Move } from 'chess.js';

export interface Ply {
  san: string;
  uci: string;
  fen: string;
}

/** Position + trait : suffit pour savoir si deux FEN décrivent la même position affichée */
export function samePosition(a: string, b: string): boolean {
  return a.split(' ').slice(0, 2).join(' ') === b.split(' ').slice(0, 2).join(' ');
}

/** Clé de position indépendante des compteurs de coups et de la notation en passant (qui varie selon les librairies) */
export function positionKey(fen: string): string {
  return fen.split(' ').slice(0, 3).join(' ');
}

function toPly(move: Move): Ply {
  return { san: move.san, uci: move.from + move.to + (move.promotion ?? ''), fen: move.after };
}

/**
 * État de la partie, source de vérité unique : l'échiquier l'affiche, l'agent l'analyse.
 * chess.js valide les coups ; on garde l'historique pour naviguer sans rappeler l'API.
 */
@Injectable({ providedIn: 'root' })
export class GameStore {
  readonly plies = signal<Ply[]>([]);
  /** Nombre de demi-coups joués dans la position affichée (on peut revenir en arrière) */
  readonly cursor = signal(0);
  readonly orientation = signal<'white' | 'black'>('white');

  readonly fen = computed(() => (this.cursor() === 0 ? DEFAULT_POSITION : this.plies()[this.cursor() - 1].fen));
  readonly turn = computed(() => (this.fen().split(' ')[1] === 'w' ? 'white' : 'black'));
  readonly lastMove = computed(() => (this.cursor() > 0 ? this.plies()[this.cursor() - 1] : null));
  readonly gameOver = computed(() => {
    const game = new Chess(this.fen());
    if (game.isCheckmate()) return 'Échec et mat';
    if (game.isStalemate()) return 'Pat';
    if (game.isDraw()) return 'Partie nulle';
    return null;
  });

  /** Joue un coup en notation SAN (clic sur une suggestion) */
  playSan(san: string): boolean {
    try {
      this.push(new Chess(this.fen()).move(san));
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Coup joué sur l'échiquier : ngx-chess-board ne donne que la FEN obtenue,
   * on retrouve le coup légal qui y mène (gère roques, prises en passant et promotions).
   */
  playFromBoardFen(boardFen: string): boolean {
    const game = new Chess(this.fen());
    const move = game.moves({ verbose: true }).find((m) => samePosition(m.after, boardFen));
    if (!move) return false;
    this.push(move);
    return true;
  }

  /** Charge une suite de coups SAN, ex. "e4 e5 Nf3 Nc6 Bb5" */
  loadLine(sans: string): void {
    const game = new Chess();
    const plies = sans.split(/\s+/).filter(Boolean).map((san) => toPly(game.move(san)));
    this.plies.set(plies);
    this.cursor.set(plies.length);
  }

  goTo(index: number): void {
    this.cursor.set(Math.max(0, Math.min(index, this.plies().length)));
  }

  first(): void {
    this.goTo(0);
  }

  previous(): void {
    this.goTo(this.cursor() - 1);
  }

  next(): void {
    this.goTo(this.cursor() + 1);
  }

  last(): void {
    this.goTo(this.plies().length);
  }

  reset(): void {
    this.plies.set([]);
    this.cursor.set(0);
  }

  flip(): void {
    this.orientation.update((o) => (o === 'white' ? 'black' : 'white'));
  }

  private push(move: Move): void {
    const ply = toPly(move);
    const cursor = this.cursor();
    const next = this.plies()[cursor];
    if (next?.uci === ply.uci) {
      // Même coup que la suite déjà connue : on avance sans effacer la ligne
      this.cursor.set(cursor + 1);
      return;
    }
    // Nouveau coup au milieu de la partie : la suite précédente est remplacée
    this.plies.set([...this.plies().slice(0, cursor), ply]);
    this.cursor.set(cursor + 1);
  }
}
