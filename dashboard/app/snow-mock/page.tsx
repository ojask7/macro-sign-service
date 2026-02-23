'use client';

import { useCallback, useRef, useState } from 'react';
import { api } from '@/lib/api';

type SignResult = {
  status: string;
  original_filename: string;
  file_size: number;
  signed_content_b64: string;
  signature: string;
  file_hash: string;
  certificate_fingerprint: string;
  certificate_subject: string;
  certificate_pem: string;
  algorithm: string;
  signed_at: string;
  requester_id: string | null;
  domain: string;
};

type Attachment = SignResult & { id: string };

const ALLOWED_EXTENSIONS = ['.vba', '.bas', '.cls', '.frm', '.vbs'];

function generateTicket() {
  return `REQ${String(Math.floor(100000 + Math.random() * 900000))}`;
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

// ─── ServiceNow Login ────────────────────────────────────────────────

function SNOWLogin({ onLogin }: { onLogin: (user: string) => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await api.login(username, password);
      api.setToken(res.access_token);
      if (typeof window !== 'undefined') {
        localStorage.setItem('mss_token', res.access_token);
      }
      onLogin(username);
    } catch (err: any) {
      setError(err.message || 'Invalid credentials');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-snow-navy flex flex-col">
      {/* SNOW top nav */}
      <header className="bg-snow-header border-b border-white/10 px-6 py-3 flex items-center gap-4">
        <div className="flex items-center gap-2 text-white">
          <svg className="w-7 h-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 6v6l4 2" />
          </svg>
          <span className="text-lg font-semibold tracking-tight">ServiceNow</span>
        </div>
        <span className="text-white/50 text-xs ml-2">Macro Signing Portal</span>
      </header>

      <div className="flex-1 flex items-center justify-center px-4">
        <div className="w-full max-w-sm">
          <h1 className="text-2xl font-bold text-white text-center mb-2">Sign in</h1>
          <p className="text-snow-muted text-center text-sm mb-6">
            Authenticate to access the macro signing request form
          </p>

          <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow-xl p-7 space-y-5">
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded px-3 py-2">
                {error}
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">
                User name
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
                autoComplete="username"
                className="snow-input"
                placeholder="admin"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="snow-input"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-snow-green hover:bg-green-700 disabled:bg-gray-400 text-white py-2 rounded font-semibold text-sm transition-colors"
            >
              {loading ? 'Authenticating…' : 'Log in'}
            </button>

            <p className="text-center text-[11px] text-gray-400 pt-1">
              Use credentials from the Macro Sign Service backend
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}

// ─── ServiceNow Header Bar ───────────────────────────────────────────

function SNOWHeader({
  user,
  onLogout,
}: {
  user: string;
  onLogout: () => void;
}) {
  return (
    <header className="bg-snow-header border-b border-white/10 px-4 py-2 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-white">
          <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 6v6l4 2" />
          </svg>
          <span className="font-semibold text-sm tracking-tight">ServiceNow</span>
        </div>
        <span className="text-white/40 text-xs">|</span>
        <span className="text-white/70 text-xs">Macro Signing Request</span>
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-snow-green flex items-center justify-center text-white text-xs font-bold uppercase">
            {user.charAt(0)}
          </div>
          <span className="text-white/80 text-xs">{user}</span>
        </div>
        <button
          onClick={onLogout}
          className="text-white/50 hover:text-white text-xs underline transition-colors"
        >
          Logout
        </button>
      </div>
    </header>
  );
}

// ─── Attachment Row ──────────────────────────────────────────────────

function AttachmentRow({
  attachment,
  onDownload,
}: {
  attachment: Attachment;
  onDownload: (a: Attachment) => void;
}) {
  return (
    <div className="flex items-center gap-3 px-3 py-2 bg-white border border-gray-200 rounded hover:bg-gray-50 transition-colors">
      <svg className="w-5 h-5 text-green-600 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
        <polyline points="14 2 14 8 20 8" />
        <path d="m9 15 2 2 4-4" />
      </svg>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 truncate">
          {attachment.original_filename}
          <span className="ml-1 text-green-700 text-xs font-normal">(signed)</span>
        </p>
        <p className="text-[11px] text-gray-500">
          {formatBytes(attachment.file_size)} &middot; {attachment.algorithm.toUpperCase()} &middot; Signed {formatDate(attachment.signed_at)}
        </p>
      </div>
      <button
        onClick={() => onDownload(attachment)}
        className="text-xs text-blue-600 hover:text-blue-800 font-medium flex-shrink-0"
      >
        Download
      </button>
    </div>
  );
}

// ─── Main ServiceNow Form ────────────────────────────────────────────

function SNOWForm({
  user,
  onLogout,
}: {
  user: string;
  onLogout: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [ticketNumber] = useState(generateTicket);
  const [file, setFile] = useState<File | null>(null);
  const [algorithm, setAlgorithm] = useState('sha256');
  const [domain, setDomain] = useState('snow-test-domain');
  const [signing, setSigning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [showDetails, setShowDetails] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const validateFile = (f: File): string | null => {
    const ext = f.name.substring(f.name.lastIndexOf('.')).toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Invalid file type "${ext}". Allowed: ${ALLOWED_EXTENSIONS.join(', ')}`;
    }
    if (f.size === 0) return 'File is empty.';
    if (f.size > 50 * 1024 * 1024) return 'File too large (max 50 MB).';
    return null;
  };

  const handleFileSelect = (f: File) => {
    setError(null);
    const err = validateFile(f);
    if (err) {
      setError(err);
      setFile(null);
      return;
    }
    setFile(f);
  };

  const handleSign = async () => {
    if (!file) return;
    setSigning(true);
    setError(null);
    setSuccessBanner(null);

    try {
      const result = await api.snowSignMacro(file, algorithm, domain, user, 'u_macro_signing');
      const attachment: Attachment = { ...result, id: crypto.randomUUID() };
      setAttachments((prev) => [attachment, ...prev]);
      setSuccessBanner(
        `Macro "${result.original_filename}" has been digitally signed and attached to ${ticketNumber}.`,
      );
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err: any) {
      setError(err.message || 'Signing failed. Please try again.');
    } finally {
      setSigning(false);
    }
  };

  const handleDownload = useCallback((a: Attachment) => {
    const bytes = atob(a.signed_content_b64);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    const blob = new Blob([arr], { type: 'application/octet-stream' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `signed_${a.original_filename}`;
    link.click();
    URL.revokeObjectURL(url);
  }, []);

  return (
    <div className="min-h-screen bg-snow-bg flex flex-col">
      <SNOWHeader user={user} onLogout={onLogout} />

      {/* Breadcrumb bar */}
      <div className="bg-gray-100 border-b border-gray-300 px-6 py-1.5 text-[11px] text-gray-500">
        Self-Service &gt; Requests &gt; Macro Signing &gt; <span className="text-gray-800 font-medium">{ticketNumber}</span>
      </div>

      {/* Success banner */}
      {successBanner && (
        <div className="bg-green-600 text-white px-6 py-2.5 text-sm flex items-center gap-2">
          <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          {successBanner}
          <button onClick={() => setSuccessBanner(null)} className="ml-auto text-white/70 hover:text-white">
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      )}

      <div className="flex-1 px-6 py-5 max-w-5xl mx-auto w-full">
        {/* Form header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-bold text-gray-900">{ticketNumber}</h1>
            <span className="snow-badge-open">Open</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleSign}
              disabled={!file || signing}
              className="bg-snow-green hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white px-4 py-1.5 rounded text-sm font-semibold transition-colors flex items-center gap-2"
            >
              {signing ? (
                <>
                  <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Signing…
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
                    <path d="m9 12 2 2 4-4" />
                  </svg>
                  Sign Macro
                </>
              )}
            </button>
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div className="bg-red-50 border border-red-300 rounded px-4 py-2.5 text-sm text-red-700 mb-4 flex items-center gap-2">
            <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" />
            </svg>
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Left column — form fields */}
          <div className="lg:col-span-2 space-y-5">
            {/* Request Details section */}
            <section className="snow-section">
              <h2 className="snow-section-title">Request Details</h2>
              <div className="grid grid-cols-2 gap-x-6 gap-y-4 mt-3">
                <div>
                  <label className="snow-label">Number</label>
                  <input type="text" readOnly value={ticketNumber} className="snow-input bg-gray-50" />
                </div>
                <div>
                  <label className="snow-label">Requested by</label>
                  <input type="text" readOnly value={user} className="snow-input bg-gray-50" />
                </div>
                <div>
                  <label className="snow-label">State</label>
                  <input
                    type="text"
                    readOnly
                    value={attachments.length > 0 ? 'Fulfilled' : 'Open'}
                    className="snow-input bg-gray-50"
                  />
                </div>
                <div>
                  <label className="snow-label">Category</label>
                  <input type="text" readOnly value="Macro Signing" className="snow-input bg-gray-50" />
                </div>
              </div>
            </section>

            {/* Signing Configuration */}
            <section className="snow-section">
              <h2 className="snow-section-title">Signing Configuration</h2>
              <div className="grid grid-cols-2 gap-x-6 gap-y-4 mt-3">
                <div>
                  <label className="snow-label">Hash Algorithm</label>
                  <select value={algorithm} onChange={(e) => setAlgorithm(e.target.value)} className="snow-input">
                    <option value="sha256">SHA-256</option>
                    <option value="sha384">SHA-384</option>
                    <option value="sha512">SHA-512</option>
                  </select>
                </div>
                <div>
                  <label className="snow-label">Signing Domain / Certificate</label>
                  <input
                    type="text"
                    value={domain}
                    onChange={(e) => setDomain(e.target.value)}
                    className="snow-input"
                  />
                </div>
              </div>
            </section>

            {/* File Upload */}
            <section className="snow-section">
              <h2 className="snow-section-title">Upload Macro File</h2>
              <div className="mt-3">
                <div
                  onClick={() => fileInputRef.current?.click()}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragOver(false);
                    const f = e.dataTransfer.files?.[0];
                    if (f) handleFileSelect(f);
                  }}
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  className={`
                    border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors
                    ${dragOver ? 'border-snow-green bg-green-50' : file ? 'border-green-300 bg-green-50' : 'border-gray-300 hover:border-gray-400 hover:bg-gray-50'}
                  `}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept={ALLOWED_EXTENSIONS.join(',')}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) handleFileSelect(f);
                    }}
                    className="hidden"
                  />
                  {file ? (
                    <div className="space-y-1">
                      <svg className="w-8 h-8 mx-auto text-green-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
                        <polyline points="14 2 14 8 20 8" />
                      </svg>
                      <p className="text-sm font-medium text-gray-900">{file.name}</p>
                      <p className="text-xs text-gray-500">{formatBytes(file.size)}</p>
                      <p className="text-xs text-snow-green">Click to replace</p>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <svg className="w-8 h-8 mx-auto text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="17 8 12 3 7 8" />
                        <line x1="12" y1="3" x2="12" y2="15" />
                      </svg>
                      <p className="text-sm font-medium text-gray-600">
                        Drag & drop your macro file here or <span className="text-blue-600">browse</span>
                      </p>
                      <p className="text-xs text-gray-400">
                        Accepted: {ALLOWED_EXTENSIONS.join(', ')} &middot; Max 50 MB
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </section>
          </div>

          {/* Right column — attachments / sidebar */}
          <div className="space-y-5">
            {/* Attachments panel */}
            <section className="snow-section">
              <h2 className="snow-section-title flex items-center gap-2">
                <svg className="w-4 h-4 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                </svg>
                Attachments
                {attachments.length > 0 && (
                  <span className="bg-snow-green text-white text-[10px] font-bold rounded-full px-1.5 py-0.5 leading-none">
                    {attachments.length}
                  </span>
                )}
              </h2>

              <div className="mt-3 space-y-2">
                {attachments.length === 0 ? (
                  <p className="text-xs text-gray-400 italic py-4 text-center">
                    No signed attachments yet. Upload and sign a macro to see it here.
                  </p>
                ) : (
                  attachments.map((a) => (
                    <div key={a.id}>
                      <AttachmentRow attachment={a} onDownload={handleDownload} />
                      <button
                        onClick={() => setShowDetails(showDetails === a.id ? null : a.id)}
                        className="text-[11px] text-blue-600 hover:text-blue-800 ml-8 mt-0.5"
                      >
                        {showDetails === a.id ? 'Hide details' : 'Show signing details'}
                      </button>

                      {showDetails === a.id && (
                        <div className="mt-2 ml-8 bg-gray-50 border border-gray-200 rounded p-3 space-y-1.5 text-[11px]">
                          <Detail label="Status" value={a.status} valueClass="text-green-700 font-semibold uppercase" />
                          <Detail label="File Hash" value={a.file_hash} mono />
                          <Detail label="Signature" value={truncate(a.signature, 64)} mono />
                          <Detail label="Algorithm" value={a.algorithm.toUpperCase()} />
                          <Detail label="Domain" value={a.domain} />
                          <Detail label="Cert Subject" value={a.certificate_subject} />
                          <Detail label="Cert Fingerprint" value={truncate(a.certificate_fingerprint, 48)} mono />
                          <Detail label="Signed At" value={formatDate(a.signed_at)} />
                          {a.requester_id && <Detail label="Requester ID" value={a.requester_id} />}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </section>

            {/* Activity / notes */}
            <section className="snow-section">
              <h2 className="snow-section-title">Activity</h2>
              <div className="mt-3 space-y-3">
                {attachments.length === 0 ? (
                  <p className="text-xs text-gray-400 italic text-center py-3">
                    No activity yet
                  </p>
                ) : (
                  attachments.map((a) => (
                    <div key={a.id} className="flex gap-2">
                      <div className="w-6 h-6 rounded-full bg-green-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                        <svg className="w-3.5 h-3.5 text-green-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      </div>
                      <div>
                        <p className="text-xs text-gray-800">
                          <span className="font-semibold">{user}</span> signed and attached{' '}
                          <span className="font-medium">{a.original_filename}</span>
                        </p>
                        <p className="text-[11px] text-gray-400">{formatDate(a.signed_at)}</p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="bg-snow-header border-t border-white/10 px-6 py-2 text-center text-[11px] text-white/30">
        Mock ServiceNow Instance &middot; Macro Sign Service &middot; Container URL: {typeof window !== 'undefined' ? window.location.origin : ''}/snow-mock
      </footer>
    </div>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────

function Detail({
  label,
  value,
  mono,
  valueClass,
}: {
  label: string;
  value: string;
  mono?: boolean;
  valueClass?: string;
}) {
  return (
    <div className="flex gap-2">
      <span className="text-gray-500 flex-shrink-0 w-28">{label}</span>
      <span className={`${mono ? 'font-mono' : ''} ${valueClass || 'text-gray-800'} break-all`}>
        {value}
      </span>
    </div>
  );
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + '…' : s;
}

// ─── Page Root ───────────────────────────────────────────────────────

export default function SNOWMockPage() {
  const [user, setUser] = useState<string | null>(null);

  const handleLogout = () => {
    setUser(null);
    api.setToken('');
    if (typeof window !== 'undefined') {
      localStorage.removeItem('mss_token');
    }
  };

  if (!user) {
    return <SNOWLogin onLogin={setUser} />;
  }

  return <SNOWForm user={user} onLogout={handleLogout} />;
}
