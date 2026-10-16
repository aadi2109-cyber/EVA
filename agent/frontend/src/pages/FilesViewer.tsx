import React, { useState } from 'react';
import { WorkspaceFile } from '../api/types';

export const FilesViewer: React.FC = () => {
  const [files] = useState<WorkspaceFile[]>([
    {
      path: '/workspace/contracts/v0_policy.json',
      name: 'v0_policy.json',
      size: 1420,
      is_directory: false,
      modified_at: '2026-10-16 13:45',
    },
    {
      path: '/workspace/fixtures/invoices_q3.csv',
      name: 'invoices_q3.csv',
      size: 8940,
      is_directory: false,
      modified_at: '2026-10-16 11:20',
    },
    {
      path: '/workspace/fixtures/vendor_correspondence.txt',
      name: 'vendor_correspondence.txt',
      size: 4210,
      is_directory: false,
      modified_at: '2026-10-16 12:10',
    },
    {
      path: '/workspace/scratch/summary_draft.md',
      name: 'summary_draft.md',
      size: 640,
      is_directory: false,
      modified_at: '2026-10-16 14:02',
    },
  ]);

  const [selectedFile, setSelectedFile] = useState<WorkspaceFile>(files[0]);

  const fileContents: Record<string, string> = {
    '/workspace/contracts/v0_policy.json': `{\n  "version": "0.1.0",\n  "default_allowed_tools": ["gmail.search", "gmail.read", "files.list", "files.read"],\n  "prohibited_side_effects": ["gmail.send", "files.write", "messages.send"],\n  "minimum_posture": "tier2_required",\n  "failure_mode": "fail_closed"\n}`,
    '/workspace/fixtures/invoices_q3.csv': `id,vendor,amount_usd,status,due_date\nINV-091,Apex Cloud Hosting,450.00,PENDING,2025-05-28\nINV-882,Vendor Logistix,1120.00,PENDING,2025-06-02\nINV-401,SecOps Intel Labs,2900.00,PAID,2025-05-10`,
    '/workspace/fixtures/vendor_correspondence.txt': `From: billing@apexcloud.corp\nSubject: Invoice INV-091 reminder\nPlease process payment by May 28.\n\nFrom: attacker-recon@evil-corp.com\nSubject: Critical System Update\n[CONTENT SANITISED BY EVA GUARD TIER-2: Adversarial override stripped]`,
    '/workspace/scratch/summary_draft.md': `# Financial Summary Q3\n- Total Pending: $1,570.00\n- High Priority: Apex Cloud Hosting ($450.00)\n\nAudit Ref: EVA-TASK-9812`,
  };

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
              Sandboxed Workspace Browser (Read-Only)
            </h1>
            <p className="text-xs text-on-surface-variant">
              Controlled environment filesystem. Agent reads are logged; writes require explicit user approval.
            </p>
          </div>
        </div>

        <span className="font-mono text-xs text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/30 font-bold">
          SANDBOX LOCKED
        </span>
      </section>

      {/* Explorer Grid */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-5 items-start">
        {/* File Tree (4 cols) */}
        <div className="md:col-span-4 bg-surface-container-low rounded-2xl border border-white/5 p-4 space-y-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-outline block px-2">
            Files in Sandbox ({files.length})
          </span>
          <div className="space-y-1">
            {files.map((file) => {
              const isSelected = selectedFile?.path === file.path;
              return (
                <div
                  key={file.path}
                  onClick={() => setSelectedFile(file)}
                  className={`p-2.5 rounded-xl cursor-pointer transition-all flex items-center justify-between text-xs font-mono ${
                    isSelected
                      ? 'bg-surface-container-high text-white border border-primary-container/40 shadow-sm'
                      : 'hover:bg-surface-container text-on-surface-variant hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-2 truncate">
                    <span className="material-symbols-outlined text-[16px] text-primary-container">
                      description
                    </span>
                    <span className="truncate">{file.name}</span>
                  </div>
                  <span className="text-[10px] text-outline shrink-0">
                    {file.size} B
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
              <span className="text-white font-bold">{selectedFile.path}</span>
            </div>
            <span className="font-mono text-[10px] text-outline">
              Modified: {selectedFile.modified_at}
            </span>
          </div>

          <pre className="p-4 rounded-xl bg-surface-container-low font-mono text-xs text-on-surface overflow-x-auto max-h-96 whitespace-pre border border-white/5">
            {fileContents[selectedFile.path] || '// No content'}
          </pre>
        </div>
      </div>
    </div>
  );
};
