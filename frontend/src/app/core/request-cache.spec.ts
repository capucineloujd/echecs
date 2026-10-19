import { Subject, defer, firstValueFrom, of, throwError } from 'rxjs';
import { RequestCache } from './request-cache';

describe('RequestCache', () => {
  it('ne refait pas un appel déjà terminé', async () => {
    const cache = new RequestCache();
    let calls = 0;
    const factory = () => defer(() => of(++calls));
    expect(await firstValueFrom(cache.get('a', factory))).toBe(1);
    expect(await firstValueFrom(cache.get('a', factory))).toBe(1);
    expect(calls).toBe(1);
  });

  it('ne garde pas les erreurs en cache', async () => {
    const cache = new RequestCache();
    let calls = 0;
    const factory = () => defer(() => (++calls === 1 ? throwError(() => new Error('boom')) : of('ok')));
    await expect(firstValueFrom(cache.get('a', factory))).rejects.toThrow('boom');
    expect(await firstValueFrom(cache.get('a', factory))).toBe('ok');
  });

  it("annule la requête en vol si plus personne ne l'écoute (coup suivant joué)", () => {
    const cache = new RequestCache();
    const pending = new Subject<string>();
    const subscription = cache.get('a', () => pending).subscribe();
    expect(pending.observed).toBe(true);
    subscription.unsubscribe();
    expect(pending.observed).toBe(false);

    // annulée : la suivante relance la requête
    let calls = 0;
    cache.get('a', () => defer(() => of(++calls))).subscribe();
    expect(calls).toBe(1);
  });

  it("évince l'entrée la moins récemment utilisée", async () => {
    const cache = new RequestCache(2);
    let calls = 0;
    const factory = () => defer(() => of(++calls));
    await firstValueFrom(cache.get('a', factory));
    await firstValueFrom(cache.get('b', factory));
    await firstValueFrom(cache.get('a', factory)); // "a" redevient récent
    await firstValueFrom(cache.get('c', factory)); // évince "b"
    expect(calls).toBe(3);
    await firstValueFrom(cache.get('a', factory));
    expect(calls).toBe(3);
    await firstValueFrom(cache.get('b', factory));
    expect(calls).toBe(4);
  });
});
