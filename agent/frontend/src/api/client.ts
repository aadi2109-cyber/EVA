import {
  User,
  SubmitApprovalRequest,
  SubmitApprovalResponse,
  Health,
  ConnectorInfo,
  WorkspaceFile,
  AuditRecord,
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE || '';

let authToken: string | null = localStorage.getItem('eva_token');

export const setAuthToken = (token: string | null) => {
  authToken = token;
  if (token) {
    localStorage.setItem('eva_token', token);
  } else {
    localStorage.removeItem('eva_token');
  }
};

export const getAuthToken = () => authToken;

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  headers.set('Content-Type', 'application/json');
  if (authToken) {
    headers.set('Authorization', `Bearer ${authToken}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errorText = await response.text();
    let errorJson;
    try {
      errorJson = JSON.parse(errorText);
    } catch {
      // ignore
    }
    throw new Error(errorJson?.detail || errorJson?.message || `HTTP ${response.status}: ${errorText}`);
  }

  return response.json();
}

const toUser = (u: any): User => ({
  id: u.id,
  email: u.email,
  role: u.role,
  name: u.name || String(u.email).split('@')[0],
});

export const api = {
  auth: {
    login: async (email: string, password: string): Promise<{ access_token: string; user: User }> => {
      const data = await request<any>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      setAuthToken(data.access_token);
      return { access_token: data.access_token, user: toUser(data.user) };
    },
    getMe: async (): Promise<User> => {
      return toUser(await request<any>('/api/me'));
    },
    logout: () => {
      setAuthToken(null);
    },
  },

  tasks: {
    create: async (user_request: string): Promise<{ task_id: string }> => {
      return request<{ task_id: string }>('/api/tasks', {
        method: 'POST',
        body: JSON.stringify({ request: user_request }),
      });
    },
    get: async (taskId: string): Promise<any> => {
      return request<any>(`/api/tasks/${taskId}`);
    },
    list: async (): Promise<any[]> => {
      return request<any[]>('/api/tasks');
    },
    cancel: async (taskId: string): Promise<void> => {
      return request<void>(`/api/tasks/${taskId}/cancel`, {
        method: 'POST',
      });
    },
  },

  approvals: {
    submit: async (
      approvalId: string,
      req: Omit<SubmitApprovalRequest, 'user_id'>
    ): Promise<SubmitApprovalResponse> => {
      return request<SubmitApprovalResponse>(`/api/approvals/${approvalId}`, {
        method: 'POST',
        body: JSON.stringify(req),
      });
    },
  },

  connectors: {
    list: async (): Promise<ConnectorInfo[]> => {
      return request<ConnectorInfo[]>('/api/connectors');
    },
    getGmailAuthUrl: async (): Promise<{ url: string }> => {
      return request<{ url: string }>('/api/connectors/gmail/auth-url');
    },
    disconnectGmail: async (): Promise<void> => {
      return request<void>('/api/connectors/gmail', {
        method: 'DELETE',
      });
    },
  },

  files: {
    list: async (path = ''): Promise<WorkspaceFile[]> => {
      const rows = await request<{ name: string; is_dir: boolean; size: number }[]>(
        `/api/files?path=${encodeURIComponent(path)}`
      );
      return rows
        .map((r) => ({
          path: path ? `${path.replace(/\/+$/, '')}/${r.name}` : r.name,
          name: r.name,
          size: r.size,
          is_directory: r.is_dir,
          modified_at: '',
        }))
        .sort((a, b) => Number(b.is_directory) - Number(a.is_directory) || a.name.localeCompare(b.name));
    },
    getContent: async (path: string): Promise<{ content: string; path: string }> => {
      return request<{ content: string; path: string }>(`/api/files/content?path=${encodeURIComponent(path)}`);
    },
  },

  health: {
    get: async (): Promise<{ backend: string; guard: Health }> => {
      return request<{ backend: string; guard: Health }>('/api/health');
    },
  },

  admin: {
    getHealth: async (): Promise<Health> => request<Health>('/api/admin/health'),
    getAudit: async (params?: { taskId?: string; eventType?: string }): Promise<AuditRecord[]> => {
      const search = new URLSearchParams({ limit: '100' });
      if (params?.taskId) search.set('task_id', params.taskId);
      if (params?.eventType) search.set('event_type', params.eventType);
      const rows = await request<any[]>(`/api/admin/audit?${search.toString()}`);
      return rows.map((r) => ({ ...r, payload: r.payload_json }));
    },
    verifyAudit: async (): Promise<{ valid: boolean; chain_length: number; tampered_event_id?: string | null; message: string }> =>
      request('/api/admin/audit/verify'),
    setKillSwitch: async (
      scope: 'tool' | 'template' | 'all_write_tools',
      target: string | null,
      enabled: boolean
    ): Promise<Health> => {
      return request<Health>('/api/admin/kill-switch', {
        method: 'POST',
        body: JSON.stringify({ scope, target, enabled }),
      });
    },
    getEvalRuns: async (): Promise<any[]> => request<any[]>('/api/admin/eval/runs'),
  },
};
