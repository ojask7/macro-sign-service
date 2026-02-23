'use client';

import { useEffect, useState } from 'react';
import AuditLogTable from '@/components/AuditLogTable';
import { api } from '@/lib/api';

interface AuditLog {
  id: string;
  action: string;
  resource_type: string;
  resource_id?: string;
  user_id?: string;
  ip_address?: string;
  details?: string;
  status: string;
  created_at: string;
}

interface AuditResp {
  logs: AuditLog[];
  total: number;
  page: number;
  per_page: number;
}

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchLogs = async (p: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = (await api.getAuditLogs(p, 50)) as AuditResp;
      setLogs(data.logs ?? []);
      setTotal(data.total ?? 0);
    } catch (err: any) {
      setError(err.message || 'Failed to load audit logs');
      setLogs([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchLogs(page); }, [page]);

  const totalPages = Math.ceil(total / 50);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Audit Logs</h1>
          <p className="text-gray-500 mt-1">Complete audit trail — live from API</p>
        </div>
      </div>

      {!loading && error && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 text-sm rounded-lg px-4 py-3">
          {error.toLowerCase().includes('403') || error.toLowerCase().includes('permission')
            ? 'Audit log access requires view_audit permission (admin/manager role).'
            : error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-3 text-gray-500 py-8">
          <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading audit logs…
        </div>
      ) : !error && (
        <>
          <AuditLogTable logs={logs} />
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500">
              {total === 0 ? 'No audit entries yet' : `${total.toLocaleString()} total entries`}
            </p>
            <div className="flex gap-2">
              <button className="btn-secondary text-sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</button>
              <button className="btn-secondary text-sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Next</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
