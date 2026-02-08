export default function CertificatesPage() {
  const certificates = [
    {
      name: 'production-signing',
      subject: 'CN=Macro Sign Prod, O=Company Inc, C=US',
      issuer: 'CN=Company CA, O=Company Inc, C=US',
      expires: '2027-01-15T00:00:00Z',
      fingerprint: 'a1b2c3d4e5f6...',
      status: 'active',
    },
    {
      name: 'staging-signing',
      subject: 'CN=Macro Sign Staging, O=Company Inc, C=US',
      issuer: 'CN=Company CA, O=Company Inc, C=US',
      expires: '2026-12-01T00:00:00Z',
      fingerprint: 'f6e5d4c3b2a1...',
      status: 'active',
    },
    {
      name: 'dev-self-signed',
      subject: 'CN=Macro Sign Service Dev, O=Development, C=US',
      issuer: 'CN=Macro Sign Service Dev, O=Development, C=US',
      expires: '2027-02-08T00:00:00Z',
      fingerprint: '112233445566...',
      status: 'active',
    },
  ];

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Certificates</h1>
          <p className="text-gray-500 mt-1">Manage signing certificates and profiles</p>
        </div>
        <button className="btn-primary text-sm">Add Certificate</button>
      </div>

      <div className="grid gap-6">
        {certificates.map((cert) => (
          <div key={cert.name} className="card p-6">
            <div className="flex items-start justify-between">
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <h3 className="text-lg font-semibold text-gray-900">{cert.name}</h3>
                  <span className="badge-success">Active</span>
                </div>
                <div className="space-y-1 text-sm text-gray-500">
                  <p><span className="font-medium text-gray-700">Subject:</span> {cert.subject}</p>
                  <p><span className="font-medium text-gray-700">Issuer:</span> {cert.issuer}</p>
                  <p>
                    <span className="font-medium text-gray-700">Expires:</span>{' '}
                    {new Date(cert.expires).toLocaleDateString('en-US', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                    })}
                  </p>
                  <p>
                    <span className="font-medium text-gray-700">Fingerprint:</span>{' '}
                    <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{cert.fingerprint}</code>
                  </p>
                </div>
              </div>
              <div className="flex gap-2">
                <button className="btn-secondary text-sm">Rotate</button>
                <button className="text-sm text-red-600 hover:text-red-700 font-medium px-3 py-2">
                  Revoke
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
