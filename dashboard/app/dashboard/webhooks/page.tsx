export default function WebhooksPage() {
  const webhooks = [
    {
      id: '1',
      name: 'CI/CD Pipeline',
      url: 'https://hooks.company.com/signing-complete',
      events: 'signing.completed,signing.failed',
      active: true,
      lastTriggered: '2026-02-08T10:30:03Z',
    },
    {
      id: '2',
      name: 'Slack Notifications',
      url: 'https://hooks.slack.com/services/T00/B00/xxxx',
      events: 'signing.failed',
      active: true,
      lastTriggered: '2026-02-07T16:45:00Z',
    },
    {
      id: '3',
      name: 'Audit System',
      url: 'https://audit.company.com/events',
      events: 'signing.completed,signing.failed,signing.requested',
      active: false,
      lastTriggered: null,
    },
  ];

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Webhooks</h1>
          <p className="text-gray-500 mt-1">Configure webhook notifications for signing events</p>
        </div>
        <button className="btn-primary text-sm">Add Webhook</button>
      </div>

      <div className="space-y-4">
        {webhooks.map((webhook) => (
          <div key={webhook.id} className="card p-6">
            <div className="flex items-start justify-between">
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <h3 className="text-lg font-semibold text-gray-900">{webhook.name}</h3>
                  {webhook.active ? (
                    <span className="badge-success">Active</span>
                  ) : (
                    <span className="badge-neutral">Inactive</span>
                  )}
                </div>
                <p className="text-sm text-gray-500 font-mono">{webhook.url}</p>
                <div className="flex gap-2 mt-2">
                  {webhook.events.split(',').map((event) => (
                    <span key={event} className="badge-info">{event}</span>
                  ))}
                </div>
                {webhook.lastTriggered && (
                  <p className="text-xs text-gray-400">
                    Last triggered:{' '}
                    {new Date(webhook.lastTriggered).toLocaleDateString('en-US', {
                      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                    })}
                  </p>
                )}
              </div>
              <div className="flex gap-2">
                <button className="btn-secondary text-sm">Test</button>
                <button className="btn-secondary text-sm">Edit</button>
                <button className="text-sm text-red-600 hover:text-red-700 font-medium px-3 py-2">
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
