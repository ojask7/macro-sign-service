export default function SettingsPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-gray-500 mt-1">Configure service settings and preferences</p>
      </div>

      {/* General Settings */}
      <div className="card">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">General</h3>
        </div>
        <div className="p-6 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Service Name</label>
              <input
                type="text"
                defaultValue="Macro Sign Service"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Environment</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500">
                <option>Development</option>
                <option>Staging</option>
                <option>Production</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Signing Settings */}
      <div className="card">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">Signing Configuration</h3>
        </div>
        <div className="p-6 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Default Algorithm</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500">
                <option>SHA-256</option>
                <option>SHA-384</option>
                <option>SHA-512</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Max File Size (MB)</label>
              <input
                type="number"
                defaultValue={50}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Allowed Extensions</label>
              <input
                type="text"
                defaultValue=".vba, .bas, .cls, .frm, .vbs, .xlsm, .xlsb, .pptm, .potm, .dotm, .xltm, .docm"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Certificate Store</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500">
                <option>Local (Development)</option>
                <option>HashiCorp Vault</option>
                <option>AWS KMS</option>
                <option>Azure Key Vault</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Rate Limiting */}
      <div className="card">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">Rate Limiting</h3>
        </div>
        <div className="p-6 space-y-6">
          <div className="flex items-center gap-3">
            <input type="checkbox" defaultChecked className="h-4 w-4 text-brand-600 focus:ring-brand-500 border-gray-300 rounded" />
            <label className="text-sm font-medium text-gray-700">Enable rate limiting</label>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Requests per Minute</label>
              <input
                type="number"
                defaultValue={60}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Burst Limit</label>
              <input
                type="number"
                defaultValue={10}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500"
              />
            </div>
          </div>
        </div>
      </div>

      {/* API Keys */}
      <div className="card">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">API Keys</h3>
        </div>
        <div className="p-6">
          <p className="text-sm text-gray-500 mb-4">
            Manage your API keys for programmatic access to the signing service.
          </p>
          <button className="btn-primary text-sm">Generate New API Key</button>
        </div>
      </div>

      {/* Save */}
      <div className="flex justify-end gap-3">
        <button className="btn-secondary">Cancel</button>
        <button className="btn-primary">Save Changes</button>
      </div>
    </div>
  );
}
