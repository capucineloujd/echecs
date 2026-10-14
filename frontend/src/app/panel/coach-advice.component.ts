import { Component, computed, inject, signal } from '@angular/core';
import { AdviceStore, ToolCall } from '../core/advice.store';

const TOOL_LABELS: Record<string, string> = {
  get_position_moves: 'Théorie Lichess',
  evaluate_position: 'Stockfish',
  search_opening_knowledge: 'Articles sur l’ouverture',
  find_videos: 'Vidéos YouTube',
};

/** Conseil rédigé par l'agent (Mistral + outils), affiché au fil de l'eau */
@Component({
  selector: 'app-coach-advice',
  template: `
    <section class="card" aria-labelledby="coach-title">
      <h2 id="coach-title">Conseil du coach</h2>

      <form class="ask" (submit)="$event.preventDefault(); ask()">
        <label class="sr-only" for="coach-question">Ta question</label>
        <input
          id="coach-question"
          type="text"
          maxlength="500"
          placeholder="Ta question (facultatif), ex. : et si je joue Nxd5 ?"
          [value]="question()"
          (input)="question.set($any($event.target).value)"
        />
        @if (advice().status === 'streaming') {
          <button type="button" (click)="store.stop()">Arrêter</button>
        } @else {
          <button type="submit" class="primary">Demander au coach</button>
        }
      </form>

      @if (advice().tools.length) {
        <ul class="tools" aria-label="Sources consultées par le coach">
          @for (tool of advice().tools; track tool.id) {
            <li [class]="tool.status">
              <span aria-hidden="true">{{ tool.status === 'running' ? '⏳' : tool.status === 'success' ? '✓' : '⚠' }}</span>
              {{ label(tool) }}
            </li>
          }
        </ul>
      }

      @switch (advice().status) {
        @case ('idle') {
          <p class="muted">Le coach regarde la position, consulte les sources utiles et t'explique quoi jouer.</p>
        }
        @case ('error') {
          <div class="error" role="alert">
            <p>{{ advice().error }}</p>
            <button type="button" (click)="ask()">Réessayer</button>
          </div>
        }
      }

      @if (advice().text) {
        <p class="advice" aria-live="polite">
          @for (part of parts(); track $index) {
            @if (part.bold) {
              <strong>{{ part.text }}</strong>
            } @else {
              {{ part.text }}
            }
          }
          @if (advice().status === 'streaming') {
            <span class="cursor" aria-hidden="true">▍</span>
          }
        </p>
      } @else if (advice().status === 'streaming') {
        <p class="muted" aria-live="polite">Le coach réfléchit…</p>
      }
    </section>
  `,
  styleUrls: ['./panel.scss', './coach-advice.scss'],
})
export class CoachAdviceComponent {
  protected readonly store = inject(AdviceStore);
  protected readonly advice = this.store.advice;
  protected readonly question = signal('');

  /** Gras Markdown (**texte**) rendu sans innerHTML */
  protected readonly parts = computed(() =>
    this.advice()
      .text.split('**')
      .map((text, i) => ({ text, bold: i % 2 === 1 })),
  );

  protected ask(): void {
    this.store.ask(this.question());
  }

  protected label(tool: ToolCall): string {
    const label = TOOL_LABELS[tool.name] ?? tool.name;
    const detail = tool.args['move_san'] ?? tool.args['opening'] ?? tool.args['query'];
    return detail ? `${label} : ${detail}` : label;
  }
}
