import React, { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../api/client';

/** Client-side guard only; the backend is authoritative. */
export const MAX_UPLOAD_BYTES = 1024 * 1024; // matches the backend upload limit (1 MB); the AGENT can read files up to 512 KB only
import { WorkspaceFile } from '../api/types';

export const FilesViewer: React.FC = () => {
  const [dir, setDir] = useState<string>('');
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<WorkspaceFile | null>(null);
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [reload, setReload] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pendingSelect, setPendingSelect] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setLoading(true);
    api.files
      .list(dir)
      .then((f) => {
        setFiles(f);
        setError(null);
        if (pendingSelect) {
          setSelectedFile(f.find((x) => x.path === pendingSelect) ?? null);
          setPendingSelect(null);
        } else {
          setSelectedFile(null);
        }
      })
      .catch((e) => setError(e?.message || 'Failed to list files'))
      .finally(() => setLoading(false));
    // pendingSelect is only read right after an upload triggers a reload
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dir, reload]);

  const onPickFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file
    if (!file) return;
    setUploadMsg(null);
    if (/[\\/]/.test(file.name)) {
      setUploadMsg({ ok: false, text: 'File names cannot contain slashes.' });
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setUploadMsg({ ok: false, text: `${file.name} is larger than ${MAX_UPLOAD_BYTES / 1024 / 1024} MB.` });
      return;
    }
    setUploading(true);
    try {
      const res = await api.files.upload(dir, file);
      setUploadMsg({ ok: true, text: `Uploaded ${file.name} (${res.size} B).` });
      setPendingSelect(res.path);
      setReload((n) => n + 1);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      const text =
        status === 404 || status === 405
          ? 'This backend does not support uploads yet.'
          : status === 409
          ? `${file.name} already exists in this folder.`
          : status === 413
          ? `${file.name} is too large for the server.`
          : (err as Error)?.message || 'Upload failed';
      setUploadMsg({ ok: false, text });
    } finally {
      setUploading(false);
    }
  };

  useEffect(() => {
    if (!selectedFile) return;
    setContent('Loading…');
    api.files
      .getContent(selectedFile.path)
      .then((r) => setContent(r.content))
      .catch((e) => setContent(`// ${e?.message || 'Failed to load file'}`));
  }, [selectedFile]);

  const openEntry = (f: WorkspaceFile) => (f.is_directory ? setDir(f.path) : setSelectedFile(f));
  const parent = dir.includes('/') ? dir.slice(0, dir.lastIndexOf('/')) : '';

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <section className="bg-surface-container-low/90 backdrop-blur-xl p-5 rounded-2xl border border-white/10 shadow-xl flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary-container/15 border border-primary-container/40 text-primary-container flex items-center justify-center">
            <span className="material-symbols-outlined text-[24px]">folder</span>
          </div>
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight">
              Sandboxed Workspace Browser
            </h1>
            <p className="text-xs text-on-surface-variant">
              Controlled environment filesystem. Uploaded files are treated as untrusted when the agent reads them; agent writes require explicit approval.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <input ref={fileInput} type="file" className="hidden" aria-label="Choose a file to upload" onChange={onPickFile} />
          <button
            type="button"
            disabled={uploading}
            onClick={() => fileInput.current?.click()}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-primary-container text-on-primary-container font-bold text-xs disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[16px]">upload</span>
            {uploading ? 'Uploading…' : 'Upload'}
          </button>
          <span className="font-mono text-xs text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/30 font-bold">
            SANDBOX LOCKED
          </span>
        </div>
      </section>

      {uploadMsg && (
        <p
          role={uploadMsg.ok ? 'status' : 'alert'}
          className={`text-xs rounded-xl px-4 py-2 border ${
            uploadMsg.ok
              ? 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30'
              : 'text-rose-300 bg-rose-500/10 border-rose-500/30'
          }`}
        >
          {uploadMsg.text}
        </p>
      )}

      {/* Explorer Grid */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-5 items-start">
        {/* File Tree (4 cols) */}
        <div className="md:col-span-4 bg-surface-container-low rounded-2xl border border-white/5 p-4 space-y-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-outline block px-2">
            Files in Sandbox ({files.length})
          </span>
          {error && <p role="alert" className="text-xs text-rose-300 px-2">{error}</p>}
          {loading && <p className="text-xs font-mono text-outline px-2">Loading…</p>}
          {!loading && !error && files.length === 0 && (
            <p className="text-xs font-mono text-outline px-2">This folder is empty.</p>
          )}
          <div className="space-y-1">
            {dir && (
              <div
                onClick={() => setDir(parent)}
                className="p-2.5 rounded-xl cursor-pointer text-xs font-mono text-on-surface-variant hover:bg-surface-container hover:text-white"
              >
                ../ <span className="text-outline">({dir})</span>
              </div>
            )}
            {files.map((file) => {
              const isSelected = selectedFile?.path === file.path;
              return (
                <div
                  key={file.path}
                  onClick={() => openEntry(file)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && openEntry(file)}
                  className={`p-2.5 rounded-xl cursor-pointer transition-all flex items-center justify-between text-xs font-mono ${
                    isSelected
                      ? 'bg-surface-container-high text-white border border-primary-container/40 shadow-sm'
                      : 'hover:bg-surface-container text-on-surface-variant hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-2 truncate">
                    <span className="material-symbols-outlined text-[16px] text-primary-container">
                      {file.is_directory ? 'folder' : 'description'}
                    </span>
                    <span className="truncate">{file.name}</span>
                  </div>
                  <span className="text-[10px] text-outline shrink-0">
                    {file.is_directory ? '' : `${file.size} B`}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* File Viewer (8 cols) */}
        <div className="md:col-span-8 bg-surface-container-lowest rounded-2xl border border-white/10 p-5 space-y-3 shadow-xl">
          <div className="flex items-center justify-between border-b border-white/5 pb-3">
            <div className="flex items-center gap-2 font-mono text-xs">
              <span className="text-outline">File:</span>
              <span className="text-white font-bold">{selectedFile?.path ?? '—'}</span>
            </div>
          </div>

          <pre className="p-4 rounded-xl bg-surface-container-low font-mono text-xs text-on-surface overflow-x-auto max-h-96 whitespace-pre border border-white/5">
            {selectedFile ? content : '// Select a file to view it (read-only, plain text)'}
          </pre>
        </div>
      </div>
    </div>
  );
};
