import { HttpErrorResponse } from '@angular/common/http';
import { Observable, TimeoutError, catchError, map, of, startWith } from 'rxjs';

export interface ApiError {
  status: number;
  message: string;
  /** Secondes à attendre avant de réessayer (en-tête Retry-After) */
  retryAfter: number | null;
}

/** État d'un appel affiché dans l'interface : chaque panneau gère son chargement et ses erreurs */
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
    const detail = typeof err.error?.detail === 'string' ? err.error.detail : null;
    const retryAfter = Number(err.headers.get('Retry-After')) || null;
    if (!detail && [502, 503, 504].includes(err.status)) {
      // Réponse du proxy nginx (backend arrêté ou en train de charger le modèle)
      return { status: err.status, message: "Le serveur de l'agent ne répond pas, il démarre peut-être encore.", retryAfter };
    }
    return { status: err.status, message: detail ?? `Erreur ${err.status}`, retryAfter };
  }
  return { status: -1, message: 'Erreur inattendue.', retryAfter: null };
}

/** Transforme un appel HTTP en flux d'états : loading, puis ok ou error (sans jamais casser le flux parent) */
export function withLoadState<T>(source: Observable<T>): Observable<LoadState<T>> {
  return source.pipe(
    map((data): LoadState<T> => ({ status: 'ok', data })),
    catchError((err) => of<LoadState<T>>({ status: 'error', error: toApiError(err) })),
    startWith<LoadState<T>>(LOADING),
  );
}
