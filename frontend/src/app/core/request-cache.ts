import { Observable, of, share, tap } from 'rxjs';

/**
 * Cache LRU de requêtes HTTP.
 * - Une position déjà analysée (retour arrière dans la partie) ne refait pas d'appel.
 * - Deux composants qui demandent la même chose partagent la même requête en vol.
 * - Si plus personne n'écoute (l'élève a joué un autre coup), la requête est annulée.
 * - Les erreurs ne sont pas mises en cache : « Réessayer » relance vraiment l'appel.
 */
export class RequestCache {
  private readonly entries = new Map<string, Observable<unknown>>();

  constructor(private readonly maxEntries = 200) {}

  get<T>(key: string, factory: () => Observable<T>): Observable<T> {
    const hit = this.entries.get(key) as Observable<T> | undefined;
    if (hit) {
      // Remise en fin de Map = entrée la plus récemment utilisée
      this.entries.delete(key);
      this.entries.set(key, hit);
      return hit;
    }
    const request: Observable<T> = factory().pipe(
      tap({
        // Réponse reçue : on garde la valeur elle-même (le flux partagé, lui, est réinitialisé
        // si l'abonné se désabonne entre la réponse et la complétion)
        next: (value) => {
          if (this.entries.has(key)) this.entries.set(key, of(value));
        },
        error: () => {
          this.entries.delete(key);
        },
        // Annulée avant la réponse : rien à garder, le prochain appel relancera la requête
        unsubscribe: () => {
          if (this.entries.get(key) === request) this.entries.delete(key);
        },
      }),
      share(),
    );
    this.entries.set(key, request);
    if (this.entries.size > this.maxEntries) {
      this.entries.delete(this.entries.keys().next().value!);
    }
    return request;
  }

  clear(): void {
    this.entries.clear();
  }
}
