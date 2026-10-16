import React from 'react';

interface PastTask {
  id: string;
  timestamp: string;
  prompt: string;
  status: 'completed' | 'held' | 'denied';
  sentencesRemoved: number;
  actionsDenied: number;
  approvals: number;
  scenarioId?: string;
}

interface HistoryProps {
  onReplayScenario: (scenarioId: string) => void;
}

export const History: React.FC<HistoryProps> = ({ onReplayScenario }) => {
  const pastTasks: PastTask[] = [
    {
      id: 'task-s1-prompt-injection',
      timestamp: 'Today at 14:02:18 UTC',
      prompt: 'Summarize my emails and list pending invoices',
      status: 'completed',
      sentencesRemoved: 1,
      actionsDenied: 0,
      approvals: 0,
      scenarioId: 'S1',
    },
    {
      id: 'task-s2-hijack-blocked',
      timestamp: 'Today at 13:58:10 UTC',
      prompt: 'Execute email archive forwarder routine',
      status: 'denied',
      sentencesRemoved: 0,
      actionsDenied: 1,
      approvals: 0,
      scenarioId: 'S2',
    },
    {
      id: 'task-s4-approval-flow',
      timestamp: 'Today at 13:45:22 UTC',
      prompt: 'Email the quarterly compliance report to bob@corp.com',
      status: 'completed',
      sentencesRemoved: 0,
      actionsDenied: 0,
      approvals: 1,
      scenarioId: 'S4',
    },
    {
      id: 'task-s7-degraded-fail-closed',
      timestamp: 'Today at 13:30:05 UTC',
      prompt: 'Scan inbound external webhooks under secondary shard',
      status: 'held',
      sentencesRemoved: 0,
      actionsDenied: 1,
      approvals: 0,
      scenarioId: 'S7',
    },
  ];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <section className="bg-surface-container-low/90 backdrop-blur-xl p-5 rounded-2xl border border-white/10 shadow-xl flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary-container/15 border border-primary-container/40 text-primary-container flex items-center justify-center">
            <span className="material-symbols-outlined text-[24px]">history</span>
          </div>
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight">
              Task Audit History & Replay Log
            </h1>
            <p className="text-xs text-on-surface-variant">
              Every past task session and its monotonic event stream is preserved for replay and verification.
            </p>
          </div>
        </div>
      </section>

      {/* Task List */}
      <div className="space-y-3">
        {pastTasks.map((t) => {
          return (
            <div
              key={t.id}
              className="p-5 rounded-2xl bg-surface-container-low border border-white/5 hover:border-white/20 transition-all shadow-lg flex flex-col md:flex-row md:items-center justify-between gap-4"
            >
              <div className="space-y-1.5 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className={`font-mono text-[10px] px-2 py-0.5 rounded-full font-bold uppercase border ${
                      t.status === 'completed'
                        ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                        : t.status === 'denied'
                        ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                        : 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30'
                    }`}
                  >
                    {t.status}
                  </span>
                  <span className="font-mono text-xs text-outline">{t.id}</span>
                  <span className="text-outline text-xs">·</span>
                  <span className="font-mono text-xs text-on-surface-variant">
                    {t.timestamp}
                  </span>
                </div>

                <p className="text-sm font-semibold text-white">{t.prompt}</p>

                <div className="flex items-center gap-3 text-xs font-mono text-outline pt-1">
                  <span>{t.sentencesRemoved} sanitizations</span>
                  <span>·</span>
                  <span>{t.actionsDenied} denials</span>
                  <span>·</span>
                  <span>{t.approvals} approvals</span>
                </div>
              </div>

              {t.scenarioId && (
                <button
                  type="button"
                  onClick={() => onReplayScenario(t.scenarioId!)}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-surface-container-high hover:bg-surface-container-highest text-primary-container text-xs font-bold border border-white/10 transition-colors shadow-sm self-start md:self-auto"
                >
                  <span className="material-symbols-outlined text-[16px]">
                    replay
                  </span>
                  <span>Replay Task Stream</span>
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
