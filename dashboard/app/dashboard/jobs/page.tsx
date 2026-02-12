'use client';

import { useState } from 'react';
import JobsTable from '@/components/JobsTable';
import UploadMacroModal from '@/components/UploadMacroModal';

const jobs = [
  {
    job_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    status: 'completed',
    original_filename: 'financial_report.vba',
    file_size: 15234,
    algorithm: 'sha256',
    created_at: '2026-02-08T10:30:00Z',
  },
  {
    job_id: 'b2c3d4e5-f6a7-8901-bcde-f12345678901',
    status: 'completed',
    original_filename: 'data_import.bas',
    file_size: 8456,
    algorithm: 'sha256',
    created_at: '2026-02-08T09:15:00Z',
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

export default function JobsPage() {
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  const handleUploadSuccess = (job: any) => {
    // In a full implementation, this would refresh the jobs list
    console.log('Signing job created:', job);
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Signing Jobs</h1>
          <p className="text-gray-500 mt-1">View and manage macro signing operations</p>
        </div>
        <div className="flex gap-3">
          <select className="btn-secondary text-sm">
            <option>All Status</option>
            <option>Completed</option>
            <option>Processing</option>
            <option>Queued</option>
            <option>Failed</option>
          </select>
          <button
            onClick={() => setIsUploadOpen(true)}
            className="btn-primary text-sm"
          >
            Upload Macro
          </button>
        </div>
      </div>

      <JobsTable jobs={jobs} title="All Signing Jobs" />

      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">Showing 1-5 of 1,247 jobs</p>
        <div className="flex gap-2">
          <button className="btn-secondary text-sm" disabled>Previous</button>
          <button className="btn-secondary text-sm">Next</button>
        </div>
      </div>

      <UploadMacroModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onSuccess={handleUploadSuccess}
      />
    </div>
  );
}
