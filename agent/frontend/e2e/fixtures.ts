import { Page, Route } from '@playwright/test';

export const USER = { id: 'u1', email: 'user@eva.local', role: 'user' };
const HEALTHY = {
  backend: { status: 'ok' },
  guard: {
    status: 'ok',
    tier2_available: true,
    t3_available: true,
    align_available: true,
    config_version: 1,
    contract_version: '0.1.0',
    kill_switch: { all_write_tools: false, tools: [] },
    metrics: {},
  },
};

type Ev = [string, Record<string, unknown>];

/** Encode events the way the backend does: id/event/data blocks with flat payloads. */
export function sse(events: Ev[]): string {
  return events
    .map(([type, payload], i) => {
      const data = { task_id: 't1', seq: i + 1, ts: '2026-01-01T00:00:00Z', ...payload };
      return `id: ${i + 1}\nevent: ${type}\ndata: ${JSON.stringify(data)}\n\n`;
    })
    .join('');
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

export interface Stub {
  events?: Ev[];
  health?: unknown;
  approvals: { id: string; body: any }[];
}

/** Stub every /api call the UI makes. Returns a record of approval submissions. */
export async function stubApi(page: Page, opts: Partial<Stub> = {}): Promise<Stub> {
  const stub: Stub = { events: [], health: HEALTHY, approvals: [], ...opts };

  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;

    if (path === '/api/auth/login') {
      const { password } = req.postDataJSON();
      return password === 'good'
        ? json(route, { access_token: 'jwt-test', token_type: 'bearer', user: USER })
        : json(route, { detail: 'Incorrect email or password' }, 401);
    }
    if (path === '/api/me') return json(route, USER);
    if (path === '/api/health') return json(route, stub.health);
    if (path === '/api/tasks' && req.method() === 'POST') return json(route, { task_id: 't1' });
    if (path === '/api/tasks') return json(route, []);
    if (path === '/api/tasks/t1/events') {
      return route.fulfill({
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
        body: sse(stub.events ?? []),
      });
    }
    if (path.startsWith('/api/approvals/')) {
      stub.approvals.push({ id: path.split('/').pop()!, body: req.postDataJSON() });
      return json(route, { status: 'approved', event_id: 'e1' });
    }
    return json(route, { detail: `unstubbed ${path}` }, 404);
  });
  return stub;
}

export async function login(page: Page, password = 'good') {
  await page.goto('/');
  await page.getByRole('textbox').first().fill('user@eva.local');
  await page.locator('input[type=password]').fill(password);
  await page.getByRole('button', { name: /Authenticate Session/ }).click();
}

export async function sendPrompt(page: Page, text: string) {
  const box = page.locator('textarea');
  await box.fill(text);
  await box.press('Enter');
}

export const S1_EVENTS: Ev[] = [
  ['task.started', {}],
  ['plan.step', { index: 1, title: 'Search invoices', status: 'running' }],
  ['tool.requested', { call_id: 'c1', tool: 'gmail.read', args: { message_id: 'msg-003' }, arg_sources: { message_id: 'user' } }],
  ['guard.decision', { call_id: 'c1', decision: 'ALLOW', reasons: [], reason_text: "Action 'gmail.read' permitted by policy" }],
  ['guard.scan', { call_id: 'c1', disposition: 'sanitized', sentences_removed: 1, tier2_available: true, warnings: [] }],
  [
    'tool.output',
    { call_id: 'c1', tool: 'gmail.read', sanitized_output: 'Invoice #1042 due Friday.', scan: { disposition: 'sanitized', fields: [{ name: 'body', text: 'x', sentences_total: 2, sentences_removed: 1, quarantined: false }] } },
  ],
  ['task.completed', { final_text: 'Pending: Invoice #1042 ($1,500).', summary: { sentences_removed: 1, actions_denied: 0, approvals: 0 } }],
];

export const S4_EVENTS: Ev[] = [
  ['task.started', {}],
  ['tool.requested', { call_id: 'c1', tool: 'gmail.send', args: { to: 'bob@corp.com', body: 'Report' }, arg_sources: { to: 'typed by user', body: 'model' } }],
  ['guard.decision', { call_id: 'c1', decision: 'REQUIRE_APPROVAL', reasons: ['SIDE_EFFECT_REQUIRES_APPROVAL'], reason_text: 'Sending email needs approval' }],
  [
    'approval.required',
    { approval: { approval_id: 'appr-1', task_id: 't1', exact_action: { tool: 'gmail.send', args: { to: 'bob@corp.com', body: 'Report' } }, arg_sources: { to: 'typed by user', body: 'model' }, action_hash: 'abcdef0123456789abcdef', expires_at: new Date(Date.now() + 600_000).toISOString() } },
  ],
];
