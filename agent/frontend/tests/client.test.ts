import { describe, it, expect, vi, afterEach } from 'vitest';
import { api, getAuthToken, setAuthToken } from '../src/api/client';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

afterEach(() => {
  vi.restoreAllMocks();
  setAuthToken(null);
});

describe('api client', () => {
  it('login stores the token and derives a display name from the email', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        json({ access_token: 'tok', token_type: 'bearer', user: { id: 'u1', email: 'user@eva.local', role: 'user' } })
      )
    );
    const { user } = await api.auth.login('user@eva.local', 'pw');
    expect(getAuthToken()).toBe('tok');
    expect(localStorage.getItem('eva_token')).toBe('tok');
    expect(user).toEqual({ id: 'u1', email: 'user@eva.local', phone: null, role: 'user', name: 'user' });
  });

  it('sends an OTP request only to EVA and includes the normalized phone', async () => {
    const f = vi.fn().mockResolvedValue(json({ message: 'If eligible, sent', otp_id: 'otp-id' }));
    vi.stubGlobal('fetch', f);
    await api.auth.sendOtp('+919876543210');
    expect(f.mock.calls[0][0]).toBe('/api/auth/otp/send');
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ phone: '+919876543210' });
    expect(f.mock.calls[0][1].headers.get('X-Api-Key')).toBeNull();
  });

  it('checks delivery status only through EVA', async () => {
    const f = vi.fn().mockResolvedValue(json({ status: 'delivered', channel: 'sms' }));
    vi.stubGlobal('fetch', f);
    await api.auth.getOtpStatus('otp-id');
    expect(f.mock.calls[0][0]).toBe('/api/auth/otp/status/otp-id');
    expect(f.mock.calls[0][1].headers.get('X-Api-Key')).toBeNull();
  });

  it('stores only EVA access token after backend confirms OTP', async () => {
    const f = vi.fn().mockResolvedValue(json({
      access_token: 'eva-jwt',
      user: { id: 'u2', email: null, phone: '+919876543210', role: 'user' },
    }));
    vi.stubGlobal('fetch', f);
    const result = await api.auth.verifyOtp('+919876543210', '001234');
    expect(f.mock.calls[0][0]).toBe('/api/auth/otp/verify');
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ phone: '+919876543210', code: '001234' });
    expect(getAuthToken()).toBe('eva-jwt');
    expect(result.user.phone).toBe('+919876543210');
    expect(result.user.name).toBe('+919876543210');
  });

  it('clears the local token and dispatches expiry on protected 401 responses', async () => {
    setAuthToken('stale-jwt');
    const expired = vi.fn();
    window.addEventListener('eva:auth-expired', expired);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ detail: 'Invalid or expired' }, 401)));
    await expect(api.tasks.list()).rejects.toThrow('Invalid or expired');
    expect(getAuthToken()).toBeNull();
    expect(expired).toHaveBeenCalledOnce();
    window.removeEventListener('eva:auth-expired', expired);
  });

  it('calls backend logout before clearing the token', async () => {
    setAuthToken('eva-jwt');
    const f = vi.fn().mockResolvedValue(json({ status: 'logged_out' }));
    vi.stubGlobal('fetch', f);
    await api.auth.logout();
    expect(f.mock.calls[0][0]).toBe('/api/auth/logout');
    expect(f.mock.calls[0][1].method).toBe('POST');
    expect(getAuthToken()).toBeNull();
  });

  it('surfaces the backend `detail` on errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ detail: 'Incorrect email or password' }, 401)));
    await expect(api.auth.login('a', 'b')).rejects.toThrow('Incorrect email or password');
  });

  it('attaches the bearer token to requests', async () => {
    setAuthToken('abc');
    const f = vi.fn().mockResolvedValue(json([]));
    vi.stubGlobal('fetch', f);
    await api.tasks.list();
    expect(new Headers(f.mock.calls[0][1].headers).get('Authorization')).toBe('Bearer abc');
  });

  it('files.list maps backend rows to paths, directories first', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        json([
          { name: 'b.txt', is_dir: false, size: 3 },
          { name: 'docs', is_dir: true, size: 0 },
        ])
      )
    );
    const files = await api.files.list('proj');
    expect(files.map((f) => [f.path, f.is_directory])).toEqual([
      ['proj/docs', true],
      ['proj/b.txt', false],
    ]);
  });

  it('approvals.submit posts only approved + edited_args (identity comes from the JWT)', async () => {
    const f = vi.fn().mockResolvedValue(json({ status: 'approved', event_id: 'e' }));
    vi.stubGlobal('fetch', f);
    await api.approvals.submit('appr-1', { approved: true, edited_args: { to: 'x@y.z' } });
    expect(f.mock.calls[0][0]).toBe('/api/approvals/appr-1');
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ approved: true, edited_args: { to: 'x@y.z' } });
  });

  it('admin.getAudit maps payload_json and sends event_type', async () => {
    const f = vi.fn().mockResolvedValue(json([{ id: 'e1', payload_json: { a: 1 } }]));
    vi.stubGlobal('fetch', f);
    const rows = await api.admin.getAudit({ eventType: 'det.scan' });
    expect(f.mock.calls[0][0]).toContain('event_type=det.scan');
    expect(rows[0].payload).toEqual({ a: 1 });
  });

  it('setKillSwitch posts scope/target/enabled', async () => {
    const f = vi.fn().mockResolvedValue(json({ status: 'ok' }));
    vi.stubGlobal('fetch', f);
    await api.admin.setKillSwitch('tool', 'gmail.send', true);
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ scope: 'tool', target: 'gmail.send', enabled: true });
  });
});
