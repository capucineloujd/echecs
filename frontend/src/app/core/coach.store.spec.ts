import { TestBed } from '@angular/core/testing';
import { Subject, of } from 'rxjs';
import { vi } from 'vitest';
import { MovesResponse, VectorSearchResponse } from './api.models';
import { CoachApiService } from './coach-api.service';
import { CoachStore } from './coach.store';
import { GameStore } from './game.store';

function moves(fen: string, opening: string | null): MovesResponse {
  return {
    fen, source: 'lichess', in_theory: true, database: 'masters', total_games: 100, moves: [], engine: null, warning: null,
    opening: opening ? { eco: 'C60', name: opening } : null,
  };
}

describe('CoachStore', () => {
  let api: { moves: ReturnType<typeof vi.fn>; openingContext: ReturnType<typeof vi.fn>; openings: ReturnType<typeof vi.fn>; evaluate: ReturnType<typeof vi.fn>; videos: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    vi.useFakeTimers();
    api = {
      moves: vi.fn((fen: string) => of(moves(fen, fen.includes('1B2p3') ? 'Ruy Lopez' : null))),
      openingContext: vi.fn(() => of({ results: [], videos: null } as unknown as VectorSearchResponse)),
      openings: vi.fn(() => of([])),
      evaluate: vi.fn(),
      videos: vi.fn(),
    };
    TestBed.configureTestingModule({ providers: [{ provide: CoachApiService, useValue: api }] });
  });

  afterEach(() => vi.useRealTimers());

  async function settle() {
    TestBed.tick();
    await vi.advanceTimersByTimeAsync(300);
    TestBed.tick();
  }

  it("n'interroge l'API que pour la position finale quand on enchaîne les coups", async () => {
    const coach = TestBed.inject(CoachStore);
    const game = TestBed.inject(GameStore);
    coach.moves();
    await settle();
    expect(api.moves).toHaveBeenCalledTimes(1);

    game.playSan('e4');
    TestBed.tick();
    game.playSan('e5');
    TestBed.tick();
    game.playSan('Nf3');
    await settle();
    expect(api.moves).toHaveBeenCalledTimes(2);
    expect(api.moves).toHaveBeenLastCalledWith(game.fen());
  });

  it("ne demande le contexte qu'une fois par ouverture, et le garde en sortant de la théorie", async () => {
    const coach = TestBed.inject(CoachStore);
    const game = TestBed.inject(GameStore);
    coach.moves();
    coach.context();

    game.loadLine('e4 e5 Nf3 Nc6 Bb5');
    await settle();
    expect(coach.openingName()).toBe('Ruy Lopez');
    expect(api.openingContext).toHaveBeenCalledTimes(1);

    game.playSan('a6'); // position sans nom d'ouverture renvoyé
    await settle();
    expect(coach.openingName()).toBe('Ruy Lopez');
    expect(api.openingContext).toHaveBeenCalledTimes(1);
  });

  it('affiche le chargement puis le résultat de la position courante', async () => {
    const pending = new Subject<MovesResponse>();
    api.moves.mockReturnValue(pending);
    const coach = TestBed.inject(CoachStore);
    coach.moves();
    await settle();
    expect(coach.moves().status).toBe('loading');
    pending.next(moves('x', null));
    TestBed.tick();
    expect(coach.moves().status).toBe('ok');
  });
});
