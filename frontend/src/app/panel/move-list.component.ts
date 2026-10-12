import { Component, computed, input, output } from '@angular/core';
import { Ply } from '../core/game.store';

/** Liste des coups numérotée, cliquable pour revenir à une position */
@Component({
  selector: 'app-move-list',
  template: `
    @if (rows().length) {
      <ol class="move-list" aria-label="Coups joués">
        @for (row of rows(); track row.number) {
          <li>
            <span class="number">{{ row.number }}.</span>
            @for (ply of row.plies; track ply.index) {
              <button type="button" [class.current]="ply.index + 1 === cursor()" (click)="select.emit(ply.index + 1)">
                {{ ply.san }}
              </button>
            }
          </li>
        }
      </ol>
    } @else {
      <p class="muted">Joue un coup sur l'échiquier pour commencer.</p>
    }
  `,
  styles: `
    .move-list {
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem 0.75rem;
      margin: 0;
      padding: 0;
      list-style: none;
      font-variant-numeric: tabular-nums;
    }
    .number {
      color: var(--muted);
      margin-right: 0.15rem;
    }
    button {
      border: 0;
      background: none;
      padding: 0.1rem 0.3rem;
      border-radius: 4px;
      font: inherit;
      color: inherit;
      cursor: pointer;
    }
    button:hover {
      background: var(--surface-2);
    }
    button.current {
      background: var(--accent);
      color: var(--on-accent);
    }
    .muted {
      color: var(--muted);
      margin: 0;
    }
  `,
})
export class MoveListComponent {
  readonly plies = input.required<Ply[]>();
  readonly cursor = input.required<number>();
  readonly select = output<number>();

  protected readonly rows = computed(() => {
    const rows: { number: number; plies: { san: string; index: number }[] }[] = [];
    this.plies().forEach((ply, index) => {
      if (index % 2 === 0) rows.push({ number: index / 2 + 1, plies: [] });
      rows[rows.length - 1].plies.push({ san: ply.san, index });
    });
    return rows;
  });
}
