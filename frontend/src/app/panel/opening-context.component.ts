import { Component, computed, input, output, signal } from '@angular/core';
import { VectorSearchResponse } from '../core/api.models';
import { LoadState } from '../core/load-state';

/** Fiche de l'ouverture : passages Wikibooks / Wikipédia retrouvés dans Milvus */
@Component({
  selector: 'app-opening-context',
  template: `
    <section class="card" aria-labelledby="context-title" [attr.aria-busy]="state().status === 'loading'">
      <h2 id="context-title">L'ouverture</h2>

      @if (openingName(); as name) {
        <p class="opening-name">
          @if (detected(); as opening) {
            <span class="eco">{{ opening.eco }}</span>
            {{ opening.name }}
            <span class="variation">{{ name }}</span>
          } @else {
            {{ name }}
          }
        </p>
      } @else {
        <p class="muted">Joue quelques coups ou choisis une ouverture : je t'expliquerai ses idées.</p>
      }

      @switch (state().status) {
        @case ('loading') {
          <ul class="skeleton tall" aria-label="Chargement du contexte"><li></li><li></li></ul>
        }
        @case ('error') {
          <div class="error" role="alert">
            <p>Contexte indisponible : {{ errorText() }}</p>
            <button type="button" (click)="retry.emit()">Réessayer</button>
          </div>
        }
        @case ('ok') {
          @let data = response()!;
          @if (!data.detected_opening || !data.results.length) {
            <p class="muted">Pas encore de fiche détaillée pour cette ouverture dans notre base.</p>
          } @else {
            <ul class="passages">
              @for (passage of data.results; track passage.url + $index) {
                <li>
                  <h3>{{ passage.section }}</h3>
                  <p [class.clamped]="!expanded().has($index)">{{ passage.text }}</p>
                  <div class="passage-footer">
                    <button type="button" class="link" (click)="toggle($index)">
                      {{ expanded().has($index) ? 'Réduire' : 'Lire la suite' }}
                    </button>
                    <a [href]="passage.url" target="_blank" rel="noopener">
                      Source : {{ passage.source === 'wikibooks' ? 'Wikibooks' : 'Wikipédia' }}
                    </a>
                  </div>
                </li>
              }
            </ul>
          }
        }
      }
    </section>
  `,
  styleUrl: './panel.scss',
})
export class OpeningContextComponent {
  readonly state = input.required<LoadState<VectorSearchResponse>>();
  readonly openingName = input<string | null>(null);
  readonly retry = output<void>();

  protected readonly expanded = signal(new Set<number>());

  protected readonly response = computed(() => {
    const s = this.state();
    return s.status === 'ok' ? s.data : null;
  });

  /** Ouverture du catalogue (nom français) ; le nom Lichess, plus précis, reste affiché dessous */
  protected readonly detected = computed(() => this.response()?.detected_opening ?? null);

  protected readonly errorText = computed(() => {
    const s = this.state();
    return s.status === 'error' ? s.error.message : '';
  });

  protected toggle(index: number): void {
    this.expanded.update((set) => {
      const next = new Set(set);
      if (!next.delete(index)) next.add(index);
      return next;
    });
  }
}
