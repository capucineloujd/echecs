import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { AgentEvent } from './agent.models';
import { AgentService } from './agent.service';
import { AdviceStore } from './advice.store';
import { GameStore } from './game.store';

describe('AdviceStore', () => {
  let stream: Subject<AgentEvent>;
  let requests: unknown[];

  beforeEach(() => {
    requests = [];
    TestBed.configureTestingModule({
      providers: [
        {
          provide: AgentService,
          useValue: {
            analyze: (request: unknown) => {
              requests.push(request);
              stream = new Subject<AgentEvent>();
              return stream;
            },
          },
        },
      ],
    });
  });

  it('envoie la position et les coups joués, puis assemble la réponse', () => {
    const game = TestBed.inject(GameStore);
    const store = TestBed.inject(AdviceStore);
    game.loadLine('e4 e5');
    store.ask('  ');

    expect(requests[0]).toEqual({ fen: game.fen(), moves: ['e4', 'e5'], question: null });
    stream.next({ event: 'token', text: 'Je regarde…' });
    stream.next({ event: 'tool_start', id: '1', name: 'get_position_moves', args: {} });
    stream.next({ event: 'tool_end', id: '1', name: 'get_position_moves', status: 'success' });
    stream.next({ event: 'token', text: 'Joue ' });
    stream.next({ event: 'token', text: 'Nf3.' });
    stream.next({ event: 'done', tools_used: ['get_position_moves'] });

    const advice = store.advice();
    expect(advice.status).toBe('done');
    expect(advice.text).toBe('Joue Nf3.'); // le texte d'avant l'appel d'outil est remplacé
    expect(advice.tools).toEqual([{ id: '1', name: 'get_position_moves', args: {}, status: 'success' }]);
  });

  it('efface le conseil et annule l’appel quand la position change', () => {
    const game = TestBed.inject(GameStore);
    const store = TestBed.inject(AdviceStore);
    store.ask(null);
    expect(stream.observed).toBe(true);

    game.playSan('e4');
    TestBed.tick();
    expect(stream.observed).toBe(false);
    expect(store.advice().status).toBe('idle');
  });

  it('signale un flux coupé sans événement final', () => {
    const store = TestBed.inject(AdviceStore);
    store.ask(null);
    stream.next({ event: 'token', text: 'Jo' });
    stream.complete();
    expect(store.advice().status).toBe('error');
  });
});
