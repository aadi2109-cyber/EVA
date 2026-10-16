import React from 'react';

interface TaskSummaryLineProps {
  summary?: {
    sentences_removed: number;
    actions_denied: number;
    approvals: number;
  };
  isCompleted?: boolean;
}

export const TaskSummaryLine: React.FC<TaskSummaryLineProps> = ({
  summary,
  isCompleted = false,
}) => {
  if (!summary && !isCompleted) return null;

  const sentences = summary?.sentences_removed || 0;
  const denied = summary?.actions_denied || 0;
  const approvals = summary?.approvals || 0;

  return (
    <div className="my-4 p-3 bg-surface-container-high/60 rounded-xl border border-primary-container/30 flex flex-wrap items-center justify-between gap-3 text-xs shadow-inner">
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-primary-container"></span>
        <span className="font-bold text-white font-mono uppercase tracking-wider">
          Task Outcome Telemetry
        </span>
      </div>

      <div className="flex items-center gap-3 font-mono text-[11px] text-on-surface-variant flex-wrap">
        <span
          className={`flex items-center gap-1.5 px-2 py-0.5 rounded ${
            sentences > 0
              ? 'bg-cyan-500/15 text-cyan-300 font-bold'
              : 'text-outline'
          }`}
        >
          <span className="material-symbols-outlined text-[13px]">
            cleaning_services
          </span>
          {sentences} {sentences === 1 ? 'sentence' : 'sentences'} removed
        </span>

        <span className="text-outline">·</span>

        <span
          className={`flex items-center gap-1.5 px-2 py-0.5 rounded ${
            denied > 0 ? 'bg-rose-500/15 text-rose-300 font-bold' : 'text-outline'
          }`}
        >
          <span className="material-symbols-outlined text-[13px]">
            block
          </span>
          {denied} {denied === 1 ? 'action' : 'actions'} denied
        </span>

        <span className="text-outline">·</span>

        <span
          className={`flex items-center gap-1.5 px-2 py-0.5 rounded ${
            approvals > 0
              ? 'bg-purple-500/15 text-purple-300 font-bold'
              : 'text-outline'
          }`}
        >
          <span className="material-symbols-outlined text-[13px]">
            verified_user
          </span>
          {approvals} {approvals === 1 ? 'approval' : 'approvals'}
        </span>
      </div>
    </div>
  );
};
