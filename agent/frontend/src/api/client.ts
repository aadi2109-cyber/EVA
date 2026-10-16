import {
  LoginResponse,
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

export const api = {
  auth: {
    login: async (email: string, password: string): Promise<LoginResponse> => {
      const data = await request<LoginResponse>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      setAuthToken(data.access_token);
      return data;
    },
    getMe: async (): Promise<User> => {
      return request<User>('/api/me');
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
      req: SubmitApprovalRequest
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
      return request<WorkspaceFile[]>(`/api/files?path=${encodeURIComponent(path)}`);
    },
    getContent: async (path: string): Promise<{ content: string; name: string }> => {
      return request<{ content: string; name: string }>(`/api/files/content?path=${encodeURIComponent(path)}`);
    },
  },

  health: {
    get: async (): Promise<{ backend: string; guard: Health }> => {
      return request<{ backend: string; guard: Health }>('/api/health');
    },
  },

  admin: {
    getAudit: async (params?: { taskId?: string; tool?: string; decision?: string }): Promise<AuditRecord[]> => {
      const search = new URLSearchParams();
      if (params?.taskId) search.set('task_id', params.taskId);
      if (params?.tool) search.set('tool', params.tool);
      if (params?.decision) search.set('decision', params.decision);
      return request<AuditRecord[]>(`/api/admin/audit?${search.toString()}`);
    },
    verifyAudit: async (): Promise<{ verified: boolean; message: string; rows_checked: number }> => {
      return request<{ verified: boolean; message: string; rows_checked: number }>('/api/admin/audit/verify');
    },
    setKillSwitch: async (
      scope: 'tool' | 'template' | 'all_write_tools',
      target: string,
      enabled: boolean
    ): Promise<{ status: string }> => {
      return request<{ status: string }>('/api/admin/kill-switch', {
        method: 'POST',
        body: JSON.stringify({ scope, target, enabled }),
      });
    },
    getEvalRuns: async (): Promise<any[]> => {
      return request<any[]>('/api/admin/eval/runs');
    },
  },
};
