import { Observable, of, share, tap } from 'rxjs';

// cache LRU des requêtes (les erreurs ne sont pas gardées)
export class RequestCache {
  private readonly entries = new Map<string, Observable<unknown>>();

  constructor(private readonly maxEntries = 200) {}

  get<T>(key: string, factory: () => Observable<T>): Observable<T> {
    const hit = this.entries.get(key) as Observable<T> | undefined;
    if (hit) {
      // on la remet à la fin (LRU)
      this.entries.delete(key);
      this.entries.set(key, hit);
      return hit;
    }
    const request: Observable<T> = factory().pipe(
      tap({
        // on garde la valeur
        next: (value) => {
          if (this.entries.has(key)) this.entries.set(key, of(value));
        },
        error: () => {
          this.entries.delete(key);
        },
        // annulée : on enlève
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
