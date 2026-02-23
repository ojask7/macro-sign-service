'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

interface CertDetail {
  name: string;
  subject: string;
  issuer: string;
  not_valid_before: string;
  not_valid_after: string;
  fingerprint_sha256: string;
  key_type: string;
}

function daysUntil(iso: string) {
  const diff = new Date(iso).getTime() - Date.now();
  return Math.floor(diff / 86_400_000);
}

export default function CertificatesPage() {
  const [certs, setCerts] = useState<CertDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const list = await api.listCerts();
        const details = await Promise.all(
          list.certificates.map((name) => api.getCertDetails(name).catch(() => null))
        );
        setCerts(details.filter(Boolean) as CertDetail[]);
      } catch (err: any) {
        setError(err.message || 'Failed to load certificates');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Certificates</h1>
          <p className="text-gray-500 mt-1">Active signing certificates — live from key store</p>
        </div>
      </div>

      {loading && (
        <div className="flex items-center gap-3 text-gray-500 py-8">
          <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading certificates…
        </div>
      )}

      {!loading && error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">{error}</div>
      )}

      {!loading && !error && certs.length === 0 && (
        <div className="card p-8 text-center text-sm text-gray-400">
          No certificates in key store yet. Run <code className="bg-gray-100 px-1 rounded">python tests/run_live_tests.py</code> to provision dev &amp; prod certificates.
        </div>
      )}

      {!loading && !error && (
        <div className="grid gap-6">
          {certs.map((cert) => {
            const days = daysUntil(cert.not_valid_after);
            const expiring = days < 30;
            const expired = days < 0;
            return (
              <div key={cert.name} className="card p-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-2 min-w-0">
                    <div className="flex items-center gap-3 flex-wrap">
                      <h3 className="text-lg font-semibold text-gray-900">{cert.name}</h3>
                      {expired
                        ? <span className="badge-error">Expired</span>
                        : expiring
                          ? <span className="badge-warning">Expiring soon</span>
                          : <span className="badge-success">Active</span>}
                      <span className="text-xs font-mono bg-gray-100 text-gray-600 px-2 py-0.5 rounded">{cert.key_type}</span>
                    </div>
                    <div className="space-y-1 text-sm text-gray-500">
                      <p><span className="font-medium text-gray-700">Subject:</span> {cert.subject}</p>
                      <p><span className="font-medium text-gray-700">Issuer:</span> {cert.issuer}</p>
                      <p>
                        <span className="font-medium text-gray-700">Valid:</span>{' '}
                        {new Date(cert.not_valid_before).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                        {' → '}
                        {new Date(cert.not_valid_after).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                        {' '}
                        <span className={expired ? 'text-red-600' : expiring ? 'text-amber-600' : 'text-green-600'}>
                          ({expired ? `expired ${Math.abs(days)}d ago` : `${days}d remaining`})
                        </span>
                      </p>
                      <p>
                        <span className="font-medium text-gray-700">SHA-256:</span>{' '}
                        <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded break-all">{cert.fingerprint_sha256}</code>
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
