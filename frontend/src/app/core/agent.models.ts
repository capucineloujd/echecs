// événements SSE de l'agent
export type AgentEvent =
  | { event: 'tool_start'; id: string; name: string; args: Record<string, unknown> }
  | { event: 'tool_end'; id: string; name: string; status: 'success' | 'error' }
  | { event: 'token'; text: string }
  | { event: 'done'; tools_used: string[] }
  | { event: 'error'; message: string };

export interface AgentRequest {
  fen: string;
  moves: string[];
  question: string | null;
}

// découpe le flux SSE, renvoie aussi le reste pas fini
export function parseSse(buffer: string): { events: AgentEvent[]; rest: string } {
  const blocks = buffer.split('\n\n');
  const rest = blocks.pop() ?? '';
  const events: AgentEvent[] = [];
  for (const block of blocks) {
    let name = '';
    let data = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('event: ')) name = line.slice(7);
      else if (line.startsWith('data: ')) data += line.slice(6);
    }
    if (name && data) events.push({ event: name, ...JSON.parse(data) } as AgentEvent);
  }
  return { events, rest };
}
