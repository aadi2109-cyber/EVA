import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

interface PastTask {
  id: string;
  request: string;
  status: string;
  created_at: string;
  final_text?: string | null;
}

interface HistoryProps {
  onReplayTask: (taskId: string, prompt: string) => void;
}

export const History: React.FC<HistoryProps> = ({ onReplayTask }) => {
  const [pastTasks, setPastTasks] = useState<PastTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.tasks
      .list()
      .then(setPastTasks)
      .catch((e) => setError(e?.message || 'Failed to load history'))
      .finally(() => setLoading(false));
  }, []);

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

      {error && <p role="alert" className="text-xs text-rose-300">{error}</p>}
      {loading && <p className="text-xs font-mono text-outline">Loading tasks…</p>}
      {!loading && !error && pastTasks.length === 0 && (
        <p className="text-xs font-mono text-outline">No tasks yet. Run one from the workspace.</p>
      )}

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
                        : t.status === 'failed' || t.status === 'cancelled'
                        ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                        : 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30'
                    }`}
                  >
                    {t.status}
                  </span>
                  <span className="font-mono text-xs text-outline">{t.id}</span>
                  <span className="text-outline text-xs">·</span>
                  <span className="font-mono text-xs text-on-surface-variant">
                    {new Date(t.created_at).toLocaleString()}
                  </span>
                </div>

                <p className="text-sm font-semibold text-white">{t.request}</p>

                {t.final_text && (
                  <p className="text-xs text-on-surface-variant line-clamp-2 whitespace-pre-wrap">{t.final_text}</p>
                )}
              </div>

              {(
                <button
                  type="button"
                  onClick={() => onReplayTask(t.id, t.request)}
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
