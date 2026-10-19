import { HttpClient, HttpDownloadProgressEvent, HttpEventType, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, filter, map, mergeMap, timeout } from 'rxjs';
import { AgentEvent, AgentRequest, parseSse } from './agent.models';

@Injectable({ providedIn: 'root' })
export class AgentService {
  private readonly http = inject(HttpClient);

  // streaming via DownloadProgress
  analyze(request: AgentRequest): Observable<AgentEvent> {
    let consumed = 0;
    let pending = '';
    return this.http
      .post('/api/v1/agent/analyze', request, { observe: 'events', reportProgress: true, responseType: 'text' })
      .pipe(
        // bloqué après 60 s
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
