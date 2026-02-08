import Link from 'next/link';

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-brand-950 to-gray-900 flex items-center justify-center">
      <div className="max-w-2xl mx-auto text-center px-6">
        {/* Logo */}
        <div className="mb-8 flex justify-center">
          <div className="w-20 h-20 bg-brand-600 rounded-2xl flex items-center justify-center shadow-lg shadow-brand-600/30">
            <svg className="w-10 h-10 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </div>
        </div>

        <h1 className="text-5xl font-bold text-white mb-4">
          Macro Sign Service
        </h1>
        <p className="text-xl text-gray-400 mb-8">
          Enterprise-grade digital signing for Office macros.
          Secure, automated, and integrated into your workflow.
        </p>

        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            href="/dashboard"
            className="bg-brand-600 hover:bg-brand-700 text-white px-8 py-3 rounded-xl font-semibold text-lg transition-all shadow-lg shadow-brand-600/30 hover:shadow-brand-600/50"
          >
            Open Dashboard
          </Link>
          <a
            href="/api/docs"
            className="bg-white/10 hover:bg-white/20 text-white border border-white/20 px-8 py-3 rounded-xl font-semibold text-lg transition-all backdrop-blur"
          >
            API Docs
          </a>
        </div>

        <div className="mt-16 grid grid-cols-1 sm:grid-cols-3 gap-6">
          <div className="bg-white/5 backdrop-blur rounded-xl p-6 border border-white/10">
            <div className="text-3xl font-bold text-white mb-1">&lt;5s</div>
            <div className="text-sm text-gray-400">Signing Latency</div>
          </div>
          <div className="bg-white/5 backdrop-blur rounded-xl p-6 border border-white/10">
            <div className="text-3xl font-bold text-white mb-1">99.9%</div>
            <div className="text-sm text-gray-400">Uptime SLA</div>
          </div>
          <div className="bg-white/5 backdrop-blur rounded-xl p-6 border border-white/10">
            <div className="text-3xl font-bold text-white mb-1">Zero</div>
            <div className="text-sm text-gray-400">Unauthorized Signs</div>
          </div>
        </div>
      </div>
    </div>
  );
}
