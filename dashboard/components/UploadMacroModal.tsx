'use client';

import { useCallback, useRef, useState } from 'react';
import { api } from '@/lib/api';

interface UploadMacroModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (job: any) => void;
}

const ALLOWED_EXTENSIONS = ['.vba', '.bas', '.cls', '.frm', '.vbs'];

export default function UploadMacroModal({ isOpen, onClose, onSuccess }: UploadMacroModalProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [algorithm, setAlgorithm] = useState('sha256');
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<any>(null);

  const reset = useCallback(() => {
    setFile(null);
    setAlgorithm('sha256');
    setDragOver(false);
    setUploading(false);
    setError(null);
    setSuccess(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  const handleClose = useCallback(() => {
    reset();
    onClose();
  }, [reset, onClose]);

  const validateFile = (f: File): string | null => {
    const ext = f.name.substring(f.name.lastIndexOf('.')).toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Invalid file type "${ext}". Allowed: ${ALLOWED_EXTENSIONS.join(', ')}`;
    }
    if (f.size === 0) {
      return 'File is empty.';
    }
    if (f.size > 50 * 1024 * 1024) {
      return 'File is too large. Maximum size is 50 MB.';
    }
    return null;
  };

  const handleFileSelect = (f: File) => {
    setError(null);
    setSuccess(null);
    const validationError = validateFile(f);
    if (validationError) {
      setError(validationError);
      setFile(null);
      return;
    }
    setFile(f);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFileSelect(f);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFileSelect(f);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setError(null);

    try {
      const result = await api.signMacro(file, algorithm);
      setSuccess(result);
      if (onSuccess) onSuccess(result);
    } catch (err: any) {
      setError(err.message || 'Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={handleClose} />

      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Upload Macro for Signing</h2>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-5">
          {/* Success state */}
          {success ? (
            <div className="text-center py-4 space-y-4">
              <div className="mx-auto w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
                <svg className="w-6 h-6 text-green-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <div>
                <p className="text-lg font-medium text-gray-900">Signing Job Created</p>
                <p className="text-sm text-gray-500 mt-1">Your macro has been submitted for signing.</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-4 text-left space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Job ID</span>
                  <code className="text-gray-900 bg-gray-200 px-2 py-0.5 rounded text-xs">
                    {success.job_id?.slice(0, 12)}...
                  </code>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Status</span>
                  <span className="text-yellow-700 font-medium">{success.status}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">File</span>
                  <span className="text-gray-900">{success.original_filename}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Algorithm</span>
                  <span className="text-gray-900 uppercase">{success.algorithm}</span>
                </div>
              </div>
              <button onClick={handleClose} className="btn-primary text-sm w-full">
                Done
              </button>
            </div>
          ) : (
            <>
              {/* Drop zone */}
              <div
                onClick={() => fileInputRef.current?.click()}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                className={`
                  border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors
                  ${dragOver
                    ? 'border-blue-400 bg-blue-50'
                    : file
                      ? 'border-green-300 bg-green-50'
                      : 'border-gray-300 hover:border-gray-400 hover:bg-gray-50'
                  }
                `}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ALLOWED_EXTENSIONS.join(',')}
                  onChange={handleInputChange}
                  className="hidden"
                />

                {file ? (
                  <div className="space-y-2">
                    <div className="mx-auto w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
                      <svg className="w-5 h-5 text-green-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
                        <polyline points="14 2 14 8 20 8" />
                      </svg>
                    </div>
                    <p className="text-sm font-medium text-gray-900">{file.name}</p>
                    <p className="text-xs text-gray-500">{formatSize(file.size)}</p>
                    <p className="text-xs text-blue-600">Click or drop to replace</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="mx-auto w-10 h-10 bg-gray-100 rounded-full flex items-center justify-center">
                      <svg className="w-5 h-5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="17 8 12 3 7 8" />
                        <line x1="12" y1="3" x2="12" y2="15" />
                      </svg>
                    </div>
                    <p className="text-sm font-medium text-gray-700">
                      Drop your macro file here or <span className="text-blue-600">browse</span>
                    </p>
                    <p className="text-xs text-gray-400">
                      Supported: {ALLOWED_EXTENSIONS.join(', ')} (max 50 MB)
                    </p>
                  </div>
                )}
              </div>

              {/* Algorithm selector */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Hash Algorithm
                </label>
                <select
                  value={algorithm}
                  onChange={(e) => setAlgorithm(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="sha256">SHA-256 (Recommended)</option>
                  <option value="sha384">SHA-384</option>
                  <option value="sha512">SHA-512</option>
                </select>
              </div>

              {/* Error message */}
              {error && (
                <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 flex items-start gap-2">
                  <svg className="w-4 h-4 mt-0.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="15" y1="9" x2="9" y2="15" />
                    <line x1="9" y1="9" x2="15" y2="15" />
                  </svg>
                  {error}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        {!success && (
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50">
            <button onClick={handleClose} className="btn-secondary text-sm">
              Cancel
            </button>
            <button
              onClick={handleUpload}
              disabled={!file || uploading}
              className={`btn-primary text-sm flex items-center gap-2 ${(!file || uploading) ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {uploading ? (
                <>
                  <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Signing...
                </>
              ) : (
                'Sign Macro'
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
