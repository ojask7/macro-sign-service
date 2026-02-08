import AuditLogTable from '@/components/AuditLogTable';

const auditLogs = [
  {
    id: '1',
    action: 'signing.requested',
    resource_type: 'signing_job',
    resource_id: 'a1b2c3d4',
    user_id: 'user-1',
    ip_address: '10.0.1.42',
    details: 'File: financial_report.vba, Size: 15234 bytes',
    status: 'success',
    created_at: '2026-02-08T10:30:00Z',
  },
  {
    id: '2',
    action: 'signing.completed',
    resource_type: 'signing_job',
    resource_id: 'a1b2c3d4',
    user_id: 'system',
    ip_address: '10.0.1.10',
    details: 'Signed with certificate: dev-cert, Algorithm: sha256',
    status: 'success',
    created_at: '2026-02-08T10:30:03Z',
  },
  {
    id: '3',
    action: 'user.login',
    resource_type: 'user',
    resource_id: 'user-1',
    ip_address: '192.168.1.100',
    details: 'Login via JWT token',
    status: 'success',
    created_at: '2026-02-08T09:00:00Z',
  },
  {
    id: '4',
    action: 'signing.failed',
    resource_type: 'signing_job',
    resource_id: 'e5f6a7b8',
    user_id: 'user-2',
    ip_address: '10.0.2.15',
    details: 'Certificate expired',
    status: 'failure',
    created_at: '2026-02-07T16:45:00Z',
  },
  {
    id: '5',
    action: 'signing.verified',
    resource_type: 'verification',
    user_id: 'user-1',
    ip_address: '10.0.1.42',
    details: 'Result: valid',
    status: 'success',
    created_at: '2026-02-07T14:20:00Z',
  },
  {
    id: '6',
    action: 'user.registered',
    resource_type: 'user',
    resource_id: 'user-3',
    ip_address: '172.16.0.5',
    details: 'New user registration',
    status: 'success',
    created_at: '2026-02-07T10:00:00Z',
  },
];

export default function AuditPage() {
  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Audit Logs</h1>
          <p className="text-gray-500 mt-1">Complete audit trail of all operations</p>
        </div>
        <div className="flex gap-3">
          <select className="btn-secondary text-sm">
            <option>All Actions</option>
            <option>signing.requested</option>
            <option>signing.completed</option>
            <option>signing.failed</option>
            <option>user.login</option>
          </select>
          <button className="btn-secondary text-sm">Export CSV</button>
        </div>
      </div>

      <AuditLogTable logs={auditLogs} />
    </div>
  );
}
