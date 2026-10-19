import { Injectable, computed, inject, signal } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { Observable, combineLatest, debounceTime, distinctUntilChanged, map, of, switchMap } from 'rxjs';
import { Evaluation, MovesResponse, OpeningRef, VectorSearchResponse, VideosResponse } from './api.models';
import { CoachApiService } from './coach-api.service';
import { GameStore, positionKey } from './game.store';
import { IDLE, LOADING, LoadState, withLoadState } from './load-state';

// attendre un peu si on joue plusieurs coups vite
const POSITION_DEBOUNCE_MS = 250;

// switchMap : un nouveau coup annule la requête d'avant
@Injectable({ providedIn: 'root' })
export class CoachStore {
  private readonly api = inject(CoachApiService);
  private readonly game = inject(GameStore);

  readonly showEvaluation = signal(false);
  private readonly movesRetry = signal(0);
  private readonly contextRetry = signal(0);
  private readonly extraVideosRequest = signal<string | null>(null);

  // nom Lichess par position
  private readonly openingByFen = signal(new Map<string, string>());

  private readonly fen$ = toObservable(this.game.fen).pipe(debounceTime(POSITION_DEBOUNCE_MS), distinctUntilChanged());

  readonly openings = toSignal(withLoadState(this.api.openings()), { initialValue: LOADING as LoadState<OpeningRef[]> });

  readonly moves = toSignal(
    combineLatest([this.fen$, toObservable(this.movesRetry)]).pipe(
      switchMap(([fen]) => withLoadState(this.api.moves(fen))),
      map((state) => {
        if (state.status === 'ok') this.rememberOpening(state.data);
        return state;
      }),
    ),
    { initialValue: LOADING as LoadState<MovesResponse> },
  );

  // garde le nom quand on sort de la théorie
  readonly openingName = computed(() => {
    const known = this.openingByFen();
    const fens = this.game.plies().slice(0, this.game.cursor()).map((p) => positionKey(p.fen));
    for (let i = fens.length - 1; i >= 0; i--) {
      const name = known.get(fens[i]);
      if (name) return name;
    }
    return null;
  });

  readonly evaluation = toSignal(
    combineLatest([this.fen$, toObservable(this.showEvaluation)]).pipe(
      switchMap(([fen, show]): Observable<LoadState<Evaluation>> => (show ? withLoadState(this.api.evaluate(fen)) : of(IDLE))),
    ),
    { initialValue: IDLE as LoadState<Evaluation> },
  );

  // un appel par ouverture, pas par coup
  readonly context = toSignal(
    combineLatest([toObservable(this.openingName).pipe(distinctUntilChanged()), toObservable(this.contextRetry)]).pipe(
      switchMap(([name]): Observable<LoadState<VectorSearchResponse>> =>
        name ? withLoadState(this.api.openingContext(name)) : of(IDLE),
      ),
    ),
    { initialValue: IDLE as LoadState<VectorSearchResponse> },
  );

  // hors catalogue : vidéos seulement si on clique (quota)
  private readonly extraVideos = toSignal(
    toObservable(this.extraVideosRequest).pipe(
      switchMap((name): Observable<LoadState<VideosResponse>> => (name ? withLoadState(this.api.videos(name)) : of(IDLE))),
    ),
    { initialValue: IDLE as LoadState<VideosResponse> },
  );

  readonly videos = computed((): LoadState<VideosResponse> => {
    const context = this.context();
    const name = this.openingName();
    if (context.status === 'ok' && context.data.videos) return { status: 'ok', data: context.data.videos };
    if (context.status === 'loading') return LOADING;
    if (name && this.extraVideosRequest() === name) return this.extraVideos();
    return IDLE;
  });

  readonly canSearchVideos = computed(() => {
    const context = this.context();
    return !!this.openingName() && context.status !== 'loading' && this.videos().status === 'idle';
  });

  retryMoves(): void {
    this.movesRetry.update((n) => n + 1);
  }

  retryContext(): void {
    this.contextRetry.update((n) => n + 1);
  }

  searchVideos(): void {
    this.extraVideosRequest.set(this.openingName());
  }

  private rememberOpening(response: MovesResponse): void {
    const name = response.opening?.name;
    const key = positionKey(response.fen);
    if (!name || this.openingByFen().get(key) === name) return;
    this.openingByFen.update((map) => new Map(map).set(key, name));
  }
}
