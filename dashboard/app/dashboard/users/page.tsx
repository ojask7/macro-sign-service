export default function UsersPage() {
  const users = [
    { id: '1', name: 'Alice Johnson', email: 'alice@company.com', role: 'admin', team: 'Engineering', status: 'active', lastLogin: '2026-02-08T10:30:00Z' },
    { id: '2', name: 'Bob Smith', email: 'bob@company.com', role: 'developer', team: 'Engineering', status: 'active', lastLogin: '2026-02-08T09:15:00Z' },
    { id: '3', name: 'Carol White', email: 'carol@company.com', role: 'manager', team: 'Finance', status: 'active', lastLogin: '2026-02-07T16:45:00Z' },
    { id: '4', name: 'Dave Brown', email: 'dave@company.com', role: 'developer', team: 'Data Analytics', status: 'active', lastLogin: '2026-02-06T14:20:00Z' },
    { id: '5', name: 'Eve Davis', email: 'eve@company.com', role: 'viewer', team: 'Operations', status: 'inactive', lastLogin: '2026-01-15T10:00:00Z' },
  ];

  const roleBadge: Record<string, string> = {
    admin: 'bg-purple-100 text-purple-800',
    manager: 'bg-blue-100 text-blue-800',
    developer: 'bg-green-100 text-green-800',
    viewer: 'bg-gray-100 text-gray-800',
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Users</h1>
          <p className="text-gray-500 mt-1">Manage user accounts and permissions</p>
        </div>
        <button className="btn-primary text-sm">Invite User</button>
      </div>

      <div className="card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-6 py-3">User</th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-6 py-3">Role</th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-6 py-3">Team</th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-6 py-3">Status</th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-6 py-3">Last Login</th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-6 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {users.map((user) => (
                <tr key={user.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4">
                    <div>
                      <p className="text-sm font-medium text-gray-900">{user.name}</p>
                      <p className="text-sm text-gray-500">{user.email}</p>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${roleBadge[user.role]}`}>
                      {user.role}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">{user.team}</td>
                  <td className="px-6 py-4">
                    <span className={user.status === 'active' ? 'badge-success' : 'badge-neutral'}>
                      {user.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {new Date(user.lastLogin).toLocaleDateString('en-US', {
                      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                    })}
                  </td>
                  <td className="px-6 py-4">
                    <button className="text-sm text-brand-600 hover:text-brand-700 font-medium">
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
