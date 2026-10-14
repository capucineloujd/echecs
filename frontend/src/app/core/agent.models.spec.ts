import { parseSse } from './agent.models';

describe('parseSse', () => {
  it('extrait les événements complets et garde le morceau inachevé', () => {
    const { events, rest } = parseSse(
      'event: tool_start\ndata: {"id":"1","name":"get_position_moves","args":{}}\n\nevent: token\ndata: {"text":"Joue "}\n\nevent: tok',
    );
    expect(events).toEqual([
      { event: 'tool_start', id: '1', name: 'get_position_moves', args: {} },
      { event: 'token', text: 'Joue ' },
    ]);
    expect(rest).toBe('event: tok');
  });

  it('reconstitue un événement coupé entre deux paquets', () => {
    const first = parseSse('event: token\ndata: {"te');
    const second = parseSse(first.rest + 'xt":"a6"}\n\n');
    expect(first.events).toEqual([]);
    expect(second.events).toEqual([{ event: 'token', text: 'a6' }]);
  });
});
