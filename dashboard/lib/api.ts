/**
 * API client for the Macro Sign Service backend.
 */

const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:8000';

interface ApiOptions {
  method?: string;
  body?: any;
  headers?: Record<string, string>;
  token?: string;
}

class ApiClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  setToken(token: string) {
    this.token = token;
  }

  private async request<T>(endpoint: string, options: ApiOptions = {}): Promise<T> {
    const { method = 'GET', body, headers = {} } = options;

    const requestHeaders: Record<string, string> = {
      'Content-Type': 'application/json',
      ...headers,
    };

    if (this.token) {
      requestHeaders['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method,
      headers: requestHeaders,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // Health
  async getHealth() {
    return this.request('/api/v1/health');
  }

  // Auth
  async login(username: string, password: string) {
    return this.request<{
      access_token: string;
      refresh_token: string;
      token_type: string;
      expires_in: number;
    }>('/api/v1/auth/login', {
      method: 'POST',
      body: { username, password },
    });
  }

  async getMe() {
    return this.request('/api/v1/auth/me');
  }

  // Signing Jobs
  async signMacro(file: File, algorithm = 'sha256', profile?: string, webhookUrl?: string) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('algorithm', algorithm);
    if (profile) formData.append('profile', profile);
    if (webhookUrl) formData.append('webhook_url', webhookUrl);

    const requestHeaders: Record<string, string> = {};
    if (this.token) {
      requestHeaders['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${this.baseUrl}/api/v1/sign`, {
      method: 'POST',
      headers: requestHeaders,
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async getSigningJobs(page = 1, perPage = 20, status?: string) {
    const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
    if (status) params.set('status_filter', status);
    return this.request(`/api/v1/sign/jobs?${params}`);
  }

  async getJobStatus(jobId: string) {
    return this.request(`/api/v1/status/${jobId}`);
  }

  // Admin
  async getUsers() {
    return this.request('/api/v1/admin/users');
  }

  async getTeams() {
    return this.request('/api/v1/admin/teams');
  }

  async getProfiles() {
    return this.request('/api/v1/admin/profiles');
  }

  async getAuditLogs(page = 1, perPage = 50) {
    return this.request(`/api/v1/admin/audit?page=${page}&per_page=${perPage}`);
  }

  async getDashboardStats() {
    return this.request('/api/v1/admin/dashboard/stats');
  }

  // Webhooks
  async getWebhooks() {
    return this.request('/api/v1/webhooks');
  }
}

export const api = new ApiClient(API_BASE_URL);
export type { ApiClient };
