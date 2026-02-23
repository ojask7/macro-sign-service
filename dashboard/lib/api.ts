/**
 * API client for the Macro Sign Service backend.
 */

// Use NEXT_PUBLIC_API_URL for client-side (browser) calls, API_BASE_URL for server-side (SSR)
const API_BASE_URL =
  typeof window !== 'undefined'
    ? (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000')
    : (process.env.API_BASE_URL || 'http://localhost:8000');

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
    // Auto-load token from localStorage for client-side calls
    if (typeof window !== 'undefined' && !this.token) {
      const stored = localStorage.getItem('mss_token');
      if (stored) this.token = stored;
    }

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

  // Certificate details (SNOW)
  async listCerts() {
    return this.request<{ certificates: string[]; count: number }>('/api/v1/snow/certs');
  }

  async snowSignMacro(
    file: File,
    algorithm = 'sha256',
    domain = 'snow-test-domain',
    requesterId?: string,
    table?: string,
  ) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('algorithm', algorithm);
    formData.append('domain', domain);
    if (requesterId) formData.append('requester_id', requesterId);
    if (table) formData.append('table', table);

    const requestHeaders: Record<string, string> = {};
    if (this.token) {
      requestHeaders['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${this.baseUrl}/api/v1/snow/sign`, {
      method: 'POST',
      headers: requestHeaders,
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Signing failed' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json() as Promise<{
      status: string;
      original_filename: string;
      file_size: number;
      signed_content_b64: string;
      signature: string;
      file_hash: string;
      certificate_fingerprint: string;
      certificate_subject: string;
      certificate_pem: string;
      algorithm: string;
      signed_at: string;
      requester_id: string | null;
      domain: string;
    }>;
  }

  async getCertDetails(name: string) {
    return this.request<{
      name: string;
      subject: string;
      issuer: string;
      serial: string;
      not_valid_before: string;
      not_valid_after: string;
      fingerprint_sha256: string;
      key_type: string;
      certificate_pem: string;
    }>(`/api/v1/snow/certs/${encodeURIComponent(name)}`);
  }
}

export const api = new ApiClient(API_BASE_URL);
export type { ApiClient };
