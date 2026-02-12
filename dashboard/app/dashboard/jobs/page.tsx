'use client';

import { useCallback, useEffect, useState } from 'react';
import JobsTable from '@/components/JobsTable';
import UploadMacroModal from '@/components/UploadMacroModal';
import { api } from '@/lib/api';

interface Job {
  job_id: string;
  status: string;
  original_filename: string;
  file_size: number;
  algorithm: string;
  created_at: string;
  completed_at?: string;
}

interface JobsResponse {
  jobs: Job[];
  total: number;
  page: number;
  per_page: number;
}

const STATUS_OPTIONS = [
  { label: 'All Status', value: '' },
  { label: 'Completed', value: 'completed' },
  { label: 'Processing', value: 'processing' },
  { label: 'Queued', value: 'queued' },
  { label: 'Failed', value: 'failed' },
];

const PER_PAGE = 20;

export default function JobsPage() {
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = (await api.getSigningJobs(page, PER_PAGE, statusFilter || undefined)) as JobsResponse;
      setJobs(data.jobs);
      setTotal(data.total);
    } catch (err: any) {
      setError(err.message || 'Failed to load signing jobs');
      setJobs([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  const handleUploadSuccess = () => {
    setIsUploadOpen(false);
    // Reset to page 1 and refresh to show the new job at the top
    setPage(1);
    fetchJobs();
  };

  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setStatusFilter(e.target.value);
    setPage(1); // Reset to first page on filter change
  };

  const totalPages = Math.ceil(total / PER_PAGE);
  const showingFrom = total === 0 ? 0 : (page - 1) * PER_PAGE + 1;
  const showingTo = Math.min(page * PER_PAGE, total);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Signing Jobs</h1>
          <p className="text-gray-500 mt-1">View and manage macro signing operations</p>
        </div>
        <div className="flex gap-3">
          <select
            value={statusFilter}
            onChange={handleStatusChange}
            className="btn-secondary text-sm"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <button
            onClick={() => setIsUploadOpen(true)}
            className="btn-primary text-sm"
          >
            Upload Macro
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={fetchJobs} className="text-red-800 underline text-sm ml-4">
            Retry
          </button>
        </div>
      )}

      {loading ? (
        <div className="card">
          <div className="px-6 py-4 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">All Signing Jobs</h3>
          </div>
          <div className="flex items-center justify-center py-16">
            <div className="flex items-center gap-3 text-gray-500">
              <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Loading jobs...
            </div>
          </div>
        </div>
      ) : (
        <JobsTable jobs={jobs} title="All Signing Jobs" />
      )}

      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {total === 0
            ? 'No jobs found'
            : `Showing ${showingFrom}-${showingTo} of ${total.toLocaleString()} jobs`
          }
        </p>
        <div className="flex gap-2">
          <button
            className="btn-secondary text-sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </button>
          <button
            className="btn-secondary text-sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
        </div>
      </div>

      <UploadMacroModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onSuccess={handleUploadSuccess}
      />
    </div>
  );
}
