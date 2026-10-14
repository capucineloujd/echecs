import { HttpClient, HttpDownloadProgressEvent, HttpEventType, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, filter, map, mergeMap, timeout } from 'rxjs';
import { AgentEvent, AgentRequest, parseSse } from './agent.models';

@Injectable({ providedIn: 'root' })
export class AgentService {
  private readonly http = inject(HttpClient);

  /**
   * Conseil du coach en streaming : HttpClient (backend fetch) expose le texte reçu au fil de l'eau
   * dans les événements DownloadProgress. On n'en extrait que les événements SSE complets.
   * Se désabonner annule la requête (et donc l'appel au LLM).
   */
  analyze(request: AgentRequest): Observable<AgentEvent> {
    let consumed = 0;
    let pending = '';
    return this.http
      .post('/api/v1/agent/analyze', request, { observe: 'events', reportProgress: true, responseType: 'text' })
      .pipe(
        // Pas de nouvel octet pendant 60 s : le flux est considéré comme bloqué
        timeout({ each: 60_000 }),
        filter((e) => e.type === HttpEventType.DownloadProgress || e.type === HttpEventType.Response),
        map((e) =>
          e.type === HttpEventType.DownloadProgress
            ? ((e as HttpDownloadProgressEvent).partialText ?? '')
            : ((e as HttpResponse<string>).body ?? ''),
        ),
        mergeMap((received) => {
          const { events, rest } = parseSse(pending + received.slice(consumed));
          consumed = received.length;
          pending = rest;
          return events;
        }),
      );
  }
}
