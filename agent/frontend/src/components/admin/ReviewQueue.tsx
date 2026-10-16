import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import { ReviewDecision, ReviewItem } from '../../api/types';

const DECISIONS: ReviewDecision[] = ['approved', 'rejected', 'investigate'];

// Fields rendered from the guard are plain text; raw flagged content is never shown.
const HIDDEN = new Set(['id', 'created_at', 'reviewer_id', 'decision', 'notes', 'decided_at']);

interface Props {
  reviewerId: string;
}

export const ReviewQueue: React.FC<Props> = ({ reviewerId }) => {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>('');
  const [adhocId, setAdhocId] = useState('');
  const [decision, setDecision] = useState<ReviewDecision>('investigate');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await api.admin.getReviewQueue());
      setError(null);
    } catch (e: any) {
      setError(e?.message || 'Failed to load review queue');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const targetId = adhocId.trim() || selected;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetId || !notes.trim()) return;
    setBusy(true);
    setDone(null);
    try {
      await api.admin.recordReviewDecision(targetId, reviewerId, decision, notes.trim());
      setDone(`Decision "${decision}" recorded for ${targetId}.`);
      setNotes('');
      setAdhocId('');
      setSelected('');
      await load();
    } catch (err: any) {
      setError(err?.message || 'Failed to record decision');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      aria-label="Review queue"
      className="p-5 sm:p-6 rounded-2xl bg-surface-container-low border border-white/5 shadow-xl space-y-4"
    >
      <div className="flex items-start justify-between gap-3 border-b border-white/5 pb-3">
        <div>
          <h3 className="font-bold text-white text-base">Review Queue</h3>
          <p className="text-xs text-on-surface-variant">
            Quarantined and held items awaiting a human decision. A decision is a record only: it never grants a tool
            any authority.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="px-3 py-1.5 rounded-lg bg-surface-container-high text-white text-xs font-bold border border-white/10"
        >
          Refresh
        </button>
      </div>

      {error && (
        <p role="alert" className="text-xs text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-lg px-3 py-2">
          {error}
        </p>
      )}
      {done && (
        <p role="status" className="text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2">
          {done}
        </p>
      )}
      {loading && <p className="text-xs font-mono text-outline">Loading review queue…</p>}
      {!loading && items.length === 0 && (
        <p className="text-xs font-mono text-outline">The review queue is empty.</p>
      )}

      {items.length > 0 && (
        <ul className="space-y-2">
          {items.map((it) => {
            const extra = Object.entries(it).filter(([k]) => !HIDDEN.has(k));
            return (
              <li
                key={it.id}
                className={`p-3 rounded-xl border text-xs space-y-1 ${
                  selected === it.id ? 'border-primary-container/50 bg-surface-container' : 'border-white/5 bg-surface-container-lowest'
                }`}
              >
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="font-mono font-bold text-primary-container">{it.id}</span>
                  {it.decision ? (
                    <span className="font-mono text-[10px] px-2 py-0.5 rounded-full border border-white/10 text-white uppercase">
                      {it.decision}
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setSelected(it.id);
                        setAdhocId('');
                      }}
                      className="font-mono text-[10px] px-2 py-0.5 rounded-full border border-amber-500/40 text-amber-300"
                    >
                      PENDING · select
                    </button>
                  )}
                </div>
                {extra.map(([k, v]) => (
                  <div key={k} className="font-mono text-on-surface-variant break-all">
                    {k}: {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                  </div>
                ))}
                {it.decision && (
                  <div className="text-on-surface-variant">
                    by {it.reviewer_id}: {it.notes}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <form onSubmit={submit} className="space-y-3 border-t border-white/5 pt-4">
        <span className="text-[11px] font-bold uppercase tracking-wider text-outline block">Record a decision</span>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="text-xs space-y-1 block">
            <span className="text-on-surface-variant">Item ID</span>
            <input
              value={adhocId || selected}
              onChange={(e) => {
                setAdhocId(e.target.value);
                setSelected('');
              }}
              placeholder="select above or enter an ID"
              className="w-full px-3 py-2 rounded-lg bg-surface-container-lowest border border-white/10 text-white font-mono"
            />
          </label>
          <label className="text-xs space-y-1 block">
            <span className="text-on-surface-variant">Decision</span>
            <select
              value={decision}
              onChange={(e) => setDecision(e.target.value as ReviewDecision)}
              className="w-full px-3 py-2 rounded-lg bg-surface-container-lowest border border-white/10 text-white font-mono"
            >
              {DECISIONS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="text-xs space-y-1 block">
          <span className="text-on-surface-variant">Notes (required)</span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="w-full px-3 py-2 rounded-lg bg-surface-container-lowest border border-white/10 text-white"
          />
        </label>
        <button
          type="submit"
          disabled={busy || !targetId || !notes.trim()}
          className="px-4 py-2 rounded-xl bg-primary-container text-on-primary-container font-bold text-xs disabled:opacity-40"
        >
          Record decision
        </button>
      </form>
    </section>
  );
};
