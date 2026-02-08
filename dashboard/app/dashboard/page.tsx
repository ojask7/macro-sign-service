import StatsCard from '@/components/StatsCard';
import JobsTable from '@/components/JobsTable';

// Demo data for the dashboard
const demoJobs = [
  {
    job_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    status: 'completed',
    original_filename: 'financial_report.vba',
    file_size: 15234,
    algorithm: 'sha256',
    created_at: '2026-02-08T10:30:00Z',
    completed_at: '2026-02-08T10:30:03Z',
  },
  {
    job_id: 'b2c3d4e5-f6a7-8901-bcde-f12345678901',
    status: 'completed',
    original_filename: 'data_import.bas',
    file_size: 8456,
    algorithm: 'sha256',
    created_at: '2026-02-08T09:15:00Z',
    completed_at: '2026-02-08T09:15:02Z',
  },
  {
    job_id: 'c3d4e5f6-a7b8-9012-cdef-123456789012',
    status: 'processing',
    original_filename: 'automation_tools.cls',
    file_size: 22100,
    algorithm: 'sha384',
    created_at: '2026-02-08T11:00:00Z',
  },
  {
    job_id: 'd4e5f6a7-b8c9-0123-defa-234567890123',
    status: 'queued',
    original_filename: 'custom_forms.frm',
    file_size: 5678,
    algorithm: 'sha256',
    created_at: '2026-02-08T11:05:00Z',
  },
  {
    job_id: 'e5f6a7b8-c9d0-1234-efab-345678901234',
    status: 'failed',
    original_filename: 'legacy_module.vba',
    file_size: 45230,
    algorithm: 'sha512',
    created_at: '2026-02-07T16:45:00Z',
  },
];

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-1">Overview of your macro signing service</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatsCard
          title="Total Signing Jobs"
          value="1,247"
          change="+12% from last month"
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
          value="98.7%"
          change="+0.3% from last month"
          changeType="positive"
          icon={
            <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          }
        />
        <StatsCard
          title="Avg Signing Time"
          value="2.3s"
          change="-0.5s from last month"
          changeType="positive"
          icon={
            <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          }
        />
        <StatsCard
          title="Active Teams"
          value="8"
          change="2 new this month"
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

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Signing Volume (7 days)</h3>
          <div className="h-48 flex items-end gap-2">
            {[45, 62, 38, 71, 55, 89, 67].map((value, index) => (
              <div key={index} className="flex-1 flex flex-col items-center gap-2">
                <div
                  className="w-full bg-brand-500 rounded-t-md transition-all hover:bg-brand-600"
                  style={{ height: `${(value / 100) * 180}px` }}
                />
                <span className="text-xs text-gray-400">
                  {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][index]}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Status Distribution</h3>
          <div className="space-y-4 mt-6">
            {[
              { label: 'Completed', value: 1230, total: 1247, color: 'bg-green-500' },
              { label: 'Failed', value: 12, total: 1247, color: 'bg-red-500' },
              { label: 'Processing', value: 3, total: 1247, color: 'bg-yellow-500' },
              { label: 'Queued', value: 2, total: 1247, color: 'bg-blue-500' },
            ].map((item) => (
              <div key={item.label} className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">{item.label}</span>
                  <span className="font-medium text-gray-900">{item.value}</span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full ${item.color} rounded-full transition-all`}
                    style={{ width: `${(item.value / item.total) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recent Jobs */}
      <JobsTable jobs={demoJobs} />
    </div>
  );
}
