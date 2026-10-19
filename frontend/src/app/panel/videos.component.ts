import { Component, computed, inject, input, linkedSignal, output } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { Video, VideosResponse } from '../core/api.models';
import { compactNumber } from '../core/format';
import { LoadState } from '../core/load-state';

const EMBED_PREFIX = 'https://www.youtube-nocookie.com/embed/';

@Component({
  selector: 'app-videos',
  template: `
    <section class="card" aria-labelledby="videos-title" [attr.aria-busy]="state().status === 'loading'">
      <h2 id="videos-title">Vidéos pour apprendre</h2>

      @switch (state().status) {
        @case ('idle') {
          @if (canSearch()) {
            <p class="muted">Cette ouverture n'est pas dans notre catalogue.</p>
            <button type="button" (click)="search.emit()">Chercher des vidéos</button>
          } @else {
            <p class="muted">Les vidéos apparaîtront dès qu'une ouverture sera reconnue.</p>
          }
        }
        @case ('loading') {
          <ul class="skeleton" aria-label="Chargement des vidéos"><li></li><li></li></ul>
        }
        @case ('error') {
          <p class="error" role="alert">Vidéos indisponibles : {{ errorText() }}</p>
        }
        @case ('ok') {
          @let data = response()!;
          @if (data.videos.length) {
            @if (playing() && embedUrl()) {
              <div class="player">
                <iframe
                  [src]="embedUrl()"
                  [title]="playing()!.title"
                  allow="accelerometer; encrypted-media; gyroscope; picture-in-picture"
                  referrerpolicy="strict-origin-when-cross-origin"
                  allowfullscreen
                ></iframe>
              </div>
            }
            <ul class="videos">
              @for (video of data.videos; track video.id) {
                <li>
                  <button type="button" class="video" [class.active]="playing()?.id === video.id" (click)="playing.set(video)">
                    @if (video.thumbnail_url) {
                      <img [src]="video.thumbnail_url" alt="" loading="lazy" width="120" height="68" />
                    }
                    <span class="video-meta">
                      <span class="video-title">{{ video.title }}</span>
                      <span class="muted">
                        {{ video.channel }} · {{ video.duration }} · {{ views(video.views) }} vues
                        @if (video.language === 'fr') { · en français }
                      </span>
                    </span>
                  </button>
                  <a class="external" [href]="video.watch_url" target="_blank" rel="noopener" [attr.aria-label]="'Ouvrir ' + video.title + ' sur YouTube'">YouTube</a>
                </li>
              }
            </ul>
          } @else {
            <p class="muted">{{ data.message ?? 'Aucune vidéo trouvée.' }}</p>
            <a [href]="data.fallback_search_url" target="_blank" rel="noopener">Chercher directement sur YouTube</a>
          }
        }
      }
    </section>
  `,
  styleUrl: './panel.scss',
})
export class VideosComponent {
  private readonly sanitizer = inject(DomSanitizer);

  readonly state = input.required<LoadState<VideosResponse>>();
  readonly canSearch = input(false);
  readonly search = output<void>();

  protected readonly response = computed(() => {
    const s = this.state();
    return s.status === 'ok' ? s.data : null;
  });

  // reset quand la liste change
  protected readonly playing = linkedSignal<VideosResponse | null, Video | null>({
    source: this.response,
    computation: () => null,
  });

  // que youtube-nocookie
  protected readonly embedUrl = computed((): SafeResourceUrl | null => {
    const url = this.playing()?.embed_url;
    return url?.startsWith(EMBED_PREFIX) ? this.sanitizer.bypassSecurityTrustResourceUrl(url) : null;
  });

  protected readonly errorText = computed(() => {
    const s = this.state();
    return s.status === 'error' ? s.error.message : '';
  });

  protected views = compactNumber;
}
