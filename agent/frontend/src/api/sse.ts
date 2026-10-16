import { SSEEventType, SSEMessage } from './types';
import { getAuthToken } from './client';

export type SSEHandler = (msg: SSEMessage) => void;

export class TaskEventStream {
  private taskId: string;
  private url: string;
  private onMessage: SSEHandler;
  private onError?: (err: any) => void;
  private abortController: AbortController | null = null;
  private lastSeq: number = -1;
  private isClosed: boolean = false;
  private reconnectTimeout: any = null;
  private reconnectAttempts: number = 0;

  constructor(taskId: string, onMessage: SSEHandler, onError?: (err: any) => void) {
    this.taskId = taskId;
    this.onMessage = onMessage;
    this.onError = onError;
    const base = import.meta.env.VITE_API_BASE || '';
    this.url = `${base}/api/tasks/${taskId}/events`;
    this.connect();
  }

  private async connect() {
    if (this.isClosed) return;
    this.abortController = new AbortController();

    const token = getAuthToken();
    const headers: Record<string, string> = {
      Accept: 'text/event-stream',
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    if (this.lastSeq >= 0) {
      headers['Last-Event-ID'] = String(this.lastSeq);
    }

    try {
      const response = await fetch(this.url, {
        headers,
        signal: this.abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`SSE HTTP error ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('ReadableStream not supported');
      }

      this.reconnectAttempts = 0;
      const decoder = new TextDecoder();
      let buffer = '';

      while (!this.isClosed) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEvent: SSEEventType = 'model.delta';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;

          if (trimmed.startsWith('event:')) {
            currentEvent = trimmed.replace('event:', '').trim() as SSEEventType;
          } else if (trimmed.startsWith('data:')) {
            const rawData = trimmed.replace('data:', '').trim();
            try {
              const parsed = JSON.parse(rawData);
              const seq = parsed.seq ?? parsed.data?.seq;

              // Ensure monotonic seq order & idempotent processing
              if (typeof seq === 'number') {
                if (seq <= this.lastSeq) {
                  // duplicate or older seq, ignore
                  continue;
                }
                this.lastSeq = seq;
              }

              const msg: SSEMessage = {
                event: currentEvent,
                data: parsed,
              };

              this.onMessage(msg);
            } catch (e) {
              console.warn('[SSE] Failed to parse SSE JSON data:', rawData, e);
            }
          }
        }
      }
    } catch (err: any) {
      if (this.isClosed || err.name === 'AbortError') return;

      console.warn('[SSE] Stream disconnected:', err);
      if (this.onError) this.onError(err);

      // Auto-reconnect with exponential backoff up to 10s
      this.reconnectAttempts++;
      const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), 10000);
      this.reconnectTimeout = setTimeout(() => {
        this.connect();
      }, delay);
    }
  }

  public close() {
    this.isClosed = true;
    if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
  }
}
