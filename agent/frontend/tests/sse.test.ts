import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { TaskEventStream } from '../src/api/sse';
import { setAuthToken } from '../src/api/client';

const enc = new TextEncoder();

function streamOf(chunks: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      chunks.forEach((x) => c.enqueue(enc.encode(x)));
      c.close();
    },
  });
  return new Response(body, { status: 200, headers: { 'content-type': 'text/event-stream' } });
}

const msg = (seq: number, type: string, extra: object = {}) =>
  `id: ${seq}\nevent: ${type}\ndata: ${JSON.stringify({ task_id: 't1', seq, ts: 'x', ...extra })}\n\n`;

const flush = () => new Promise((r) => setTimeout(r, 20));

describe('TaskEventStream', () => {
  beforeEach(() => setAuthToken('jwt-123'));
  afterEach(() => vi.restoreAllMocks());

  it('parses events split across chunk boundaries, in seq order', async () => {
    const full = msg(1, 'model.delta', { text: 'hi' }) + msg(2, 'task.completed', { summary: {} });
    const cut = 30;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamOf([full.slice(0, cut), full.slice(cut)])));
    const got: any[] = [];
    new TaskEventStream('t1', (m) => got.push(m));
    await flush();
    expect(got.map((g) => [g.event, g.data.seq])).toEqual([
      ['model.delta', 1],
      ['task.completed', 2],
    ]);
  });

  it('drops duplicate or older seq (idempotent)', async () => {
    const chunks = [msg(1, 'model.delta', { text: 'a' }), msg(1, 'model.delta', { text: 'a' }), msg(2, 'task.completed')];
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamOf(chunks)));
    const got: any[] = [];
    new TaskEventStream('t1', (m) => got.push(m));
    await flush();
    expect(got).toHaveLength(2);
  });

  it('sends the bearer token and does not reconnect after a terminal event', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamOf([msg(1, 'task.completed', { summary: {} })]));
    vi.stubGlobal('fetch', fetchMock);
    new TaskEventStream('t1', () => {});
    await flush();
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer jwt-123');
  });

  it('reconnects with Last-Event-ID when the stream drops before a terminal event', async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(streamOf([msg(1, 'model.delta', { text: 'a' }), msg(2, 'model.delta', { text: 'b' })]))
      .mockResolvedValueOnce(streamOf([msg(3, 'task.completed', { summary: {} })]));
    vi.stubGlobal('fetch', fetchMock);
    const got: any[] = [];
    const onError = vi.fn();
    new TaskEventStream('t1', (m) => got.push(m), onError);
    await vi.advanceTimersByTimeAsync(5000);
    vi.useRealTimers();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect((fetchMock.mock.calls[1][1].headers as Record<string, string>)['Last-Event-ID']).toBe('2');
    expect(got.map((g) => g.data.seq)).toEqual([1, 2, 3]);
    expect(onError).toHaveBeenCalled();
  });
});
