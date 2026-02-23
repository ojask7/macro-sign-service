'use client';

import { useEffect, useState } from 'react';
import StatsCard from '@/components/StatsCard';
import JobsTable from '@/components/JobsTable';
import { api } from '@/lib/api';

interface Stats {
  total_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  average_signing_time_ms: number;
  active_users: number;
  active_teams: number;
  recent_jobs: any[];
}

interface JobsResp {
  jobs: any[];
  total: number;
}

function pct(n: number, d: number) {
  if (!d) return '0%';
  return `${((n / d) * 100).toFixed(1)}%`;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [totalJobs, setTotalJobs] = useState(0);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      // Try admin stats first (requires view_analytics permission)
      try {
        const s = (await api.getDashboardStats()) as any;
        setStats(s);
        setJobs(s.recent_jobs ?? []);
      } catch (err: any) {
        if (err.message?.includes('403') || err.message?.toLowerCase().includes('permission')) {
          setNotice('Dashboard stats require admin/analytics access. Showing your recent jobs instead.');
        }
        // Fall back to jobs list
        try {
          const jr = (await api.getSigningJobs(1, 10)) as JobsResp;
          setJobs(jr.jobs ?? []);
          setTotalJobs(jr.total ?? 0);
        } catch {
          // nothing
        }
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const total = stats?.total_jobs ?? totalJobs;
  const completed = stats?.completed_jobs ?? jobs.filter((j) => j.status === 'completed').length;
  const failed = stats?.failed_jobs ?? jobs.filter((j) => j.status === 'failed').length;
  const avgMs = stats?.average_signing_time_ms ?? null;
  const recentJobs = stats?.recent_jobs ?? jobs;

  // Build status distribution from available data
  const processing = jobs.filter((j) => j.status === 'processing').length;
  const queued = jobs.filter((j) => j.status === 'queued').length;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-1">Live overview of your macro signing service</p>
      </div>

      {notice && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 text-sm rounded-lg px-4 py-3">
          {notice}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-3 text-gray-500 py-12">
          <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading live data…
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <StatsCard
              title="Total Signing Jobs"
              value={total.toLocaleString()}
              change={`${completed} completed`}
              changeType="positive"
              icon={
                <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
              }
            />
            <StatsCard
              title="Success Rate"
              value={total > 0 ? pct(completed, total) : '—'}
              change={`${failed} failed`}
              changeType={failed === 0 ? 'positive' : 'negative'}
              icon={
                <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
              }
            />
            <StatsCard
              title="Avg Signing Time"
              value={avgMs != null ? `${(avgMs / 1000).toFixed(2)}s` : '—'}
              change="per file"
              changeType="neutral"
              icon={
                <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
              }
            />
            <StatsCard
              title="Active Users"
              value={stats?.active_users?.toString() ?? '—'}
              change={`${stats?.active_teams ?? '—'} teams`}
              changeType="neutral"
              icon={
                <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 21a8 8 0 0 0-16 0" />
                  <circle cx="10" cy="8" r="5" />
                  <path d="M22 20c0-3.37-2-6.5-4-8a5 5 0 0 0-.45-8.3" />
                </svg>
              }
            />
          </div>

          {/* Status distribution */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="card p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Status Distribution</h3>
              <div className="space-y-4 mt-2">
                {[
                  { label: 'Completed', value: completed, color: 'bg-green-500' },
                  { label: 'Failed', value: failed, color: 'bg-red-500' },
                  { label: 'Processing', value: processing, color: 'bg-yellow-500' },
                  { label: 'Queued', value: queued, color: 'bg-blue-500' },
                ].map((item) => (
                  <div key={item.label} className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">{item.label}</span>
                      <span className="font-medium text-gray-900">{item.value}</span>
                    </div>
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${item.color} rounded-full transition-all`}
                        style={{ width: total > 0 ? `${Math.max(2, (item.value / total) * 100)}%` : '0%' }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="card p-6 flex flex-col justify-center items-center text-center">
              <div className="text-5xl font-bold text-brand-600 mb-2">{total}</div>
              <div className="text-gray-500 text-sm">Total macros signed</div>
              <div className="mt-4 text-xs text-gray-400">Live data from API</div>
            </div>
          </div>

          <JobsTable jobs={recentJobs} title="Recent Signing Jobs" />
        </>
      )}
    </div>
  );
}
