import { HttpErrorResponse, HttpHeaders, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';
import { CoachApiService, fenToPath } from './coach-api.service';
import { toApiError } from './load-state';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

describe('CoachApiService', () => {
  let api: CoachApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    api = TestBed.inject(CoachApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('met la FEN dans le chemin avec des "_" à la place des espaces', () => {
    expect(fenToPath(START)).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR_w_KQkq_-_0_1');
  });

  it('ne rappelle pas /moves pour une position déjà analysée', async () => {
    const first = firstValueFrom(api.moves(START));
    http.expectOne(`/api/v1/moves/${fenToPath(START)}`).flush({ fen: START, moves: [] });
    await first;

    const again = await firstValueFrom(api.moves(START));
    expect(again.fen).toBe(START);
    http.expectNone(() => true);
  });

  it("interroge le RAG avec le nom de l'ouverture", () => {
    api.openingContext('Ruy Lopez').subscribe();
    const req = http.expectOne((r) => r.url === '/api/v1/vector-search');
    expect(req.request.params.get('opening')).toBe('Ruy Lopez');
    expect(req.request.params.get('top_k')).toBe('3');
    req.flush({});
  });

  it('encode le nom d’ouverture pour /videos', () => {
    api.videos("King's Pawn Game").subscribe();
    http.expectOne("/api/v1/videos/King's%20Pawn%20Game").flush({});
  });
});

describe('toApiError', () => {
  it('lit le détail et le Retry-After du backend', () => {
    const error = toApiError(
      new HttpErrorResponse({
        status: 503,
        error: { detail: 'Lichess limite les requêtes' },
        headers: new HttpHeaders({ 'Retry-After': '42' }),
      }),
    );
    expect(error).toEqual({ status: 503, message: 'Lichess limite les requêtes', retryAfter: 42 });
  });

  it('lit le détail quand le corps d’erreur est du texte (requête de streaming)', () => {
    const error = toApiError(new HttpErrorResponse({ status: 503, error: '{"detail":"Coach indisponible"}' }));
    expect(error.message).toBe('Coach indisponible');
  });

  it('traduit la page 502 de nginx quand le backend est arrêté', () => {
    const error = toApiError(new HttpErrorResponse({ status: 502, error: '<html>Bad Gateway</html>' }));
    expect(error.message).toContain('ne répond pas');
  });

  it('signale un serveur injoignable', () => {
    expect(toApiError(new HttpErrorResponse({ status: 0 })).message).toContain('injoignable');
  });
});
