import { TestBed } from '@angular/core/testing';
import { Chess } from 'chess.js';
import { GameStore, positionKey } from './game.store';

describe('GameStore', () => {
  let game: GameStore;

  beforeEach(() => {
    game = TestBed.inject(GameStore);
  });

  it('joue un coup SAN et met à jour la FEN', () => {
    expect(game.playSan('e4')).toBe(true);
    expect(game.fen()).toContain('4P3');
    expect(game.turn()).toBe('black');
    expect(game.plies().map((p) => p.uci)).toEqual(['e2e4']);
  });

  it('refuse un coup illégal sans changer la partie', () => {
    expect(game.playSan('e5')).toBe(false);
    expect(game.plies()).toEqual([]);
  });

  it("retrouve le coup joué sur l'échiquier à partir de sa FEN (roque inclus)", () => {
    game.loadLine('e4 e5 Nf3 Nc6 Bc4 Bc5');
    const afterCastle = new Chess(game.fen());
    afterCastle.move('O-O');
    // La librairie d'échiquier peut renvoyer des compteurs différents : seules position et trait comptent
    const boardFen = afterCastle.fen().replace(/ \d+ \d+$/, ' 0 1');
    expect(game.playFromBoardFen(boardFen)).toBe(true);
    expect(game.lastMove()?.san).toBe('O-O');
  });

  it("refuse une FEN d'échiquier qui ne correspond à aucun coup légal", () => {
    expect(game.playFromBoardFen('8/8/8/8/8/8/8/K6k w - - 0 1')).toBe(false);
    expect(game.cursor()).toBe(0);
  });

  it('navigue dans la partie et remplace la suite quand on joue un autre coup', () => {
    game.loadLine('e4 e5 Nf3');
    game.previous();
    game.previous();
    expect(game.cursor()).toBe(1);

    // Même coup que la suite connue : la ligne est conservée
    game.playSan('e5');
    expect(game.plies().length).toBe(3);
    expect(game.cursor()).toBe(2);

    // Autre coup : la suite est remplacée
    game.previous();
    game.playSan('c5');
    expect(game.plies().map((p) => p.san)).toEqual(['e4', 'c5']);
  });

  it('détecte le mat', () => {
    game.loadLine('f3 e5 g4 Qh4#');
    expect(game.gameOver()).toBe('Échec et mat');
  });

  it('positionKey ignore les compteurs de coups', () => {
    expect(positionKey('8/8/8/8/8/8/8/K6k w - - 3 40')).toBe(positionKey('8/8/8/8/8/8/8/K6k w - - 0 1'));
  });
});
