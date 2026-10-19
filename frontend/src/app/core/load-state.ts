import { HttpErrorResponse } from '@angular/common/http';
import { Observable, TimeoutError, catchError, map, of, startWith } from 'rxjs';

export interface ApiError {
  status: number;
  message: string;
  // Retry-After
  retryAfter: number | null;
}

export type LoadState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ok'; data: T }
  | { status: 'error'; error: ApiError };

export const IDLE: LoadState<never> = { status: 'idle' };
export const LOADING: LoadState<never> = { status: 'loading' };

export function toApiError(err: unknown): ApiError {
  if (err instanceof TimeoutError) {
    return { status: 0, message: 'Le serveur met trop de temps à répondre.', retryAfter: null };
  }
  if (err instanceof HttpErrorResponse) {
    if (err.status === 0) {
      return { status: 0, message: 'Serveur injoignable : vérifie ta connexion ou que le backend est démarré.', retryAfter: null };
    }
    const detail = errorDetail(err.error);
    const retryAfter = Number(err.headers.get('Retry-After')) || null;
    if (!detail && [502, 503, 504].includes(err.status)) {
      // erreur nginx, backend pas prêt
      return { status: err.status, message: "Le serveur de l'agent ne répond pas, il démarre peut-être encore.", retryAfter };
    }
    return { status: err.status, message: detail ?? `Erreur ${err.status}`, retryAfter };
  }
  return { status: -1, message: 'Erreur inattendue.', retryAfter: null };
}

// detail de FastAPI (string pour le SSE)
function errorDetail(body: unknown): string | null {
  if (typeof body === 'string') {
    try {
      body = JSON.parse(body);
    } catch {
      return null;
    }
  }
  const detail = (body as { detail?: unknown } | null)?.detail;
  return typeof detail === 'string' ? detail : null;
}

// loading puis ok ou error
export function withLoadState<T>(source: Observable<T>): Observable<LoadState<T>> {
  return source.pipe(
    map((data): LoadState<T> => ({ status: 'ok', data })),
    catchError((err) => of<LoadState<T>>({ status: 'error', error: toApiError(err) })),
    startWith<LoadState<T>>(LOADING),
  );
}
