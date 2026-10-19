import { Injectable, effect, inject, signal, untracked } from '@angular/core';
import { Subscription } from 'rxjs';
import { AgentService } from './agent.service';
import { GameStore } from './game.store';
import { toApiError } from './load-state';

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: 'running' | 'success' | 'error';
}

export interface Advice {
  status: 'idle' | 'streaming' | 'done' | 'error';
  fen: string | null;
  text: string;
  tools: ToolCall[];
  error: string | null;
}

const IDLE_ADVICE: Advice = { status: 'idle', fen: null, text: '', tools: [], error: null };

@Injectable({ providedIn: 'root' })
export class AdviceStore {
  private readonly agent = inject(AgentService);
  private readonly game = inject(GameStore);
  private subscription: Subscription | null = null;

  readonly advice = signal<Advice>(IDLE_ADVICE);

  constructor() {
    // on efface le conseil quand la position change
    effect(() => {
      const fen = this.game.fen();
      untracked(() => {
        if (this.advice().fen !== null && this.advice().fen !== fen) this.reset();
      });
    });
  }

  ask(question: string | null): void {
    this.subscription?.unsubscribe();
    const fen = this.game.fen();
    const moves = this.game.plies().slice(0, this.game.cursor()).map((p) => p.san);
    this.advice.set({ ...IDLE_ADVICE, status: 'streaming', fen });

    this.subscription = this.agent.analyze({ fen, moves, question: question?.trim() || null }).subscribe({
      next: (event) => {
        this.advice.update((a) => {
          switch (event.event) {
            case 'tool_start':
              // texte avant un outil = brouillon
              return { ...a, text: '', tools: [...a.tools, { id: event.id, name: event.name, args: event.args, status: 'running' }] };
            case 'tool_end':
              return { ...a, tools: a.tools.map((t) => (t.id === event.id ? { ...t, status: event.status } : t)) };
            case 'token':
              return { ...a, text: a.text + event.text };
            case 'done':
              return { ...a, status: 'done' };
            case 'error':
              return { ...a, status: 'error', error: event.message };
          }
        });
      },
      error: (err) => this.advice.update((a) => ({ ...a, status: 'error', error: toApiError(err).message })),
      complete: () =>
        this.advice.update((a) =>
          a.status === 'streaming' ? { ...a, status: 'error', error: 'La réponse du coach a été interrompue.' } : a,
        ),
    });
  }

  stop(): void {
    this.subscription?.unsubscribe();
    this.advice.update((a) => (a.status === 'streaming' ? { ...a, status: a.text ? 'done' : 'idle' } : a));
  }

  reset(): void {
    this.subscription?.unsubscribe();
    this.advice.set(IDLE_ADVICE);
  }
}
