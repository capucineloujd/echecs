import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, timeout } from 'rxjs';
import { Evaluation, MovesResponse, OpeningRef, VectorSearchResponse, VideosResponse } from './api.models';
import { RequestCache } from './request-cache';

const API = '/api/v1';

// espaces remplacés par _ dans l'URL
export function fenToPath(fen: string): string {
  return fen.trim().replace(/ /g, '_');
}

@Injectable({ providedIn: 'root' })
export class CoachApiService {
  private readonly http = inject(HttpClient);
  private readonly cache = new RequestCache();

  openings(): Observable<OpeningRef[]> {
    return this.cache.get('openings', () => this.http.get<OpeningRef[]>(`${API}/openings`).pipe(timeout(10_000)));
  }

  moves(fen: string): Observable<MovesResponse> {
    return this.cache.get(`moves:${fen}`, () =>
      this.http.get<MovesResponse>(`${API}/moves/${fenToPath(fen)}`).pipe(timeout(20_000)),
    );
  }

  evaluate(fen: string): Observable<Evaluation> {
    return this.cache.get(`eval:${fen}`, () =>
      this.http.get<Evaluation>(`${API}/evaluate/${fenToPath(fen)}`).pipe(timeout(20_000)),
    );
  }

  openingContext(openingName: string): Observable<VectorSearchResponse> {
    const params = { query: `Idées, plans et pièges de l'ouverture ${openingName}`, opening: openingName, top_k: 3 };
    return this.cache.get(`context:${openingName}`, () =>
      this.http.get<VectorSearchResponse>(`${API}/vector-search`, { params }).pipe(timeout(60_000)),
    );
  }

  videos(opening: string): Observable<VideosResponse> {
    return this.cache.get(`videos:${opening}`, () =>
      this.http.get<VideosResponse>(`${API}/videos/${encodeURIComponent(opening)}`).pipe(timeout(30_000)),
    );
  }
}
