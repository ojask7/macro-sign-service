export default function TeamsPage() {
  const teams = [
    { id: '1', name: 'Finance', description: 'Financial reporting team', members: 12, profiles: 3, active: true },
    { id: '2', name: 'Engineering', description: 'Software development team', members: 28, profiles: 5, active: true },
    { id: '3', name: 'Data Analytics', description: 'Data science and analytics', members: 8, profiles: 2, active: true },
    { id: '4', name: 'Operations', description: 'IT operations team', members: 6, profiles: 1, active: true },
  ];

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Teams</h1>
          <p className="text-gray-500 mt-1">Manage teams and their signing profiles</p>
        </div>
        <button className="btn-primary text-sm">Create Team</button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {teams.map((team) => (
          <div key={team.id} className="card p-6 hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">{team.name}</h3>
                <p className="text-sm text-gray-500 mt-1">{team.description}</p>
              </div>
              <span className="badge-success">Active</span>
            </div>
            <div className="flex gap-6 text-sm">
              <div>
                <span className="text-gray-500">Members</span>
                <p className="font-semibold text-gray-900">{team.members}</p>
              </div>
              <div>
                <span className="text-gray-500">Profiles</span>
                <p className="font-semibold text-gray-900">{team.profiles}</p>
              </div>
            </div>
            <div className="mt-4 pt-4 border-t border-gray-100 flex gap-3">
              <button className="text-sm text-brand-600 hover:text-brand-700 font-medium">
                Manage Members
              </button>
              <button className="text-sm text-brand-600 hover:text-brand-700 font-medium">
                View Profiles
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
