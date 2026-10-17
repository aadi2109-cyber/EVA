import { SSEEventType, SSEMessage } from './types';
import { getAuthToken, setAuthToken } from './client';

const TERMINAL = new Set(['task.completed', 'task.failed', 'task.held', 'task.cancelled']);

export type SSEHandler = (msg: SSEMessage) => void;

export class TaskEventStream {
  private taskId: string;
  private url: string;
  private onMessage: SSEHandler;
  private onError?: (err: any) => void;
  private abortController: AbortController | null = null;
  private lastSeq: number = -1;
  private isClosed: boolean = false;
  private finished: boolean = false;
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
        if (response.status === 401) {
          setAuthToken(null);
          window.dispatchEvent(new CustomEvent('eva:auth-expired'));
          this.close();
          return;
        }
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
        // SSE messages are separated by a blank line; a message may span chunks.
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() || '';

        for (const block of blocks) {
          let currentEvent = 'message';
          const dataLines: string[] = [];
          for (const line of block.split(/\r?\n/)) {
            if (line.startsWith('event:')) currentEvent = line.slice(6).trim();
            else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
          }
          if (dataLines.length === 0) continue;
          const rawData = dataLines.join('\n');
          try {
            const parsed = JSON.parse(rawData);
            const seq = parsed.seq;
            // Monotonic seq order & idempotent processing
            if (typeof seq === 'number') {
              if (seq <= this.lastSeq) continue;
              this.lastSeq = seq;
            }
            if (TERMINAL.has(currentEvent)) this.finished = true;
            this.onMessage({ event: currentEvent as SSEEventType, data: parsed });
          } catch (e) {
            console.warn('[SSE] Failed to parse SSE JSON data:', rawData, e);
          }
        }
      }
      // Server closes the stream after the terminal task event; any other end is a drop.
      if (this.finished) {
        this.isClosed = true;
        return;
      }
      throw new Error('SSE stream ended before task finished');
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
