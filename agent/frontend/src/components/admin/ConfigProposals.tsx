import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import { ConfigProposal } from '../../api/types';

type Field =
  | { key: string; label: string; kind: 'select'; options: string[] }
  | { key: string; label: string; kind: 'number'; min: number; max: number; step: number }
  | { key: string; label: string; kind: 'bool' };

const FIELDS: Field[] = [
  { key: 'minimum_detector_posture', label: 'Minimum detector posture', kind: 'select', options: ['tier2_required', 'tier1_ok_readonly'] },
  { key: 'failure_mode', label: 'Failure mode', kind: 'select', options: ['fail_closed', 'tier1_only_warning'] },
  { key: 'block_threshold', label: 'Block threshold', kind: 'number', min: 0, max: 1, step: 0.01 },
  { key: 't3_enabled', label: 'T3 (LAYA) enabled', kind: 'bool' },
  { key: 'align_enabled', label: 'ALIGN enabled', kind: 'bool' },
];

interface Props {
  currentAdminId: string;
}

export const ConfigProposals: React.FC<Props> = ({ currentAdminId }) => {
  const [config, setConfig] = useState<Record<string, any> | null>(null);
  const [proposals, setProposals] = useState<ConfigProposal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [justification, setJustification] = useState('');

  const load = useCallback(async () => {
    try {
      const [c, list] = await Promise.all([api.admin.getConfig(), api.admin.listProposals()]);
      setConfig(c);
      setProposals(list);
      setError(null);
    } catch (e: any) {
      setError(e?.message || 'Failed to load configuration');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const changes = useMemo(() => {
    const out: Record<string, any> = {};
    for (const [k, v] of Object.entries(draft)) {
      if (config && v !== undefined && v !== config[k]) out[k] = v;
    }
    return out;
  }, [draft, config]);
  const hasChanges = Object.keys(changes).length > 0;

  const propose = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!hasChanges || !justification.trim()) return;
    setBusy(true);
    setNotice(null);
    try {
      const p = await api.admin.proposeConfig(changes, justification.trim());
      setNotice(`Proposal ${p.proposal_id} created. A different admin must approve it before it takes effect.`);
      setDraft({});
      setJustification('');
      await load();
    } catch (err: any) {
      setError(err?.message || 'Failed to create proposal');
    } finally {
      setBusy(false);
    }
  };

  const reject = async (id: string, own: boolean) => {
    setBusy(true);
    setNotice(null);
    try {
      await api.admin.rejectProposal(id);
      setNotice(`Proposal ${id} ${own ? 'withdrawn' : 'rejected'}. Nothing was changed.`);
      await load();
    } catch (err: any) {
      setError(err?.message || 'Rejection failed');
    } finally {
      setBusy(false);
    }
  };

  const approve = async (id: string) => {
    setBusy(true);
    setNotice(null);
    try {
      await api.admin.approveProposal(id);
      setNotice(`Proposal ${id} approved and applied.`);
      await load();
    } catch (err: any) {
      // e.g. four-eyes violation: surfaced verbatim, the guard decides
      setError(err?.message || 'Approval failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      aria-label="Configuration proposals"
      className="p-5 sm:p-6 rounded-2xl bg-surface-container-low border border-white/5 shadow-xl space-y-4"
    >
      <div className="border-b border-white/5 pb-3">
        <h3 className="font-bold text-white text-base">Guard Configuration & Four-Eyes Proposals</h3>
        <p className="text-xs text-on-surface-variant">
          Configuration changes are proposals. A second admin (not the proposer) must approve before anything changes.
        </p>
      </div>

      {error && (
        <p role="alert" className="text-xs text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-lg px-3 py-2">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2">
          {notice}
        </p>
      )}

      <div>
        <span className="text-[11px] font-bold uppercase tracking-wider text-outline block mb-2">
          Active configuration {config ? `(v${config.version})` : ''}
        </span>
        {!config ? (
          <p className="text-xs font-mono text-outline">Loading…</p>
        ) : (
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
            {FIELDS.map((f) => (
              <div key={f.key} className="p-2.5 rounded-lg bg-surface-container-lowest border border-white/5 flex justify-between gap-2">
                <dt className="text-on-surface-variant">{f.key}</dt>
                <dd className="text-white">{String(config[f.key])}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>

      <form onSubmit={propose} className="space-y-3 border-t border-white/5 pt-4">
        <span className="text-[11px] font-bold uppercase tracking-wider text-outline block">Propose a change</span>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {FIELDS.map((f) => {
            const current = draft[f.key] ?? config?.[f.key];
            return (
              <label key={f.key} className="text-xs space-y-1 block">
                <span className="text-on-surface-variant">{f.label}</span>
                {f.kind === 'select' && (
                  <select
                    value={String(current ?? '')}
                    onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                    className="w-full px-3 py-2 rounded-lg bg-surface-container-lowest border border-white/10 text-white font-mono"
                  >
                    {f.options.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </select>
                )}
                {f.kind === 'number' && (
                  <input
                    type="number"
                    min={f.min}
                    max={f.max}
                    step={f.step}
                    value={current ?? ''}
                    onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value === '' ? undefined : Number(e.target.value) }))}
                    className="w-full px-3 py-2 rounded-lg bg-surface-container-lowest border border-white/10 text-white font-mono"
                  />
                )}
                {f.kind === 'bool' && (
                  <select
                    value={String(current ?? '')}
                    onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value === 'true' }))}
                    className="w-full px-3 py-2 rounded-lg bg-surface-container-lowest border border-white/10 text-white font-mono"
                  >
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                )}
              </label>
            );
          })}
        </div>
        <label className="text-xs space-y-1 block">
          <span className="text-on-surface-variant">Justification (required)</span>
          <textarea
            value={justification}
            onChange={(e) => setJustification(e.target.value)}
            rows={2}
            className="w-full px-3 py-2 rounded-lg bg-surface-container-lowest border border-white/10 text-white"
          />
        </label>
        {hasChanges && (
          <p className="text-[11px] font-mono text-amber-300">Pending change: {JSON.stringify(changes)}</p>
        )}
        <button
          type="submit"
          disabled={busy || !hasChanges || !justification.trim()}
          className="px-4 py-2 rounded-xl bg-primary-container text-on-primary-container font-bold text-xs disabled:opacity-40"
        >
          Submit proposal
        </button>
      </form>

      <div className="border-t border-white/5 pt-4 space-y-2">
        <span className="text-[11px] font-bold uppercase tracking-wider text-outline block">Proposals</span>
        {proposals.length === 0 && <p className="text-xs font-mono text-outline">No proposals yet.</p>}
        {proposals.map((p) => {
          const own = p.proposed_by === currentAdminId;
          return (
            <div key={p.proposal_id} className="p-3 rounded-xl bg-surface-container-lowest border border-white/5 text-xs space-y-1">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <span className="font-mono font-bold text-primary-container">{p.proposal_id}</span>
                <span
                  className={`font-mono text-[10px] px-2 py-0.5 rounded-full border uppercase ${
                    p.status === 'approved'
                      ? 'border-emerald-500/40 text-emerald-300'
                      : p.status === 'rejected'
                      ? 'border-rose-500/40 text-rose-300'
                      : 'border-amber-500/40 text-amber-300'
                  }`}
                >
                  {p.status}
                </span>
              </div>
              <div className="font-mono text-white break-all">{JSON.stringify(p.changes)}</div>
              <div className="text-on-surface-variant">
                {p.justification} · proposed by {own ? 'you' : p.proposed_by}
              </div>
              {p.status === 'pending' && (
                <div className="pt-1 flex items-center gap-2 flex-wrap">
                  {own ? (
                    <span className="text-[11px] text-outline">Waiting for a different admin to approve.</span>
                  ) : (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void approve(p.proposal_id)}
                      className="px-3 py-1.5 rounded-lg bg-purple-500/20 text-purple-200 border border-purple-500/40 font-bold text-[11px] disabled:opacity-40"
                    >
                      Approve as second admin
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void reject(p.proposal_id, own)}
                    className="px-3 py-1.5 rounded-lg bg-rose-500/15 text-rose-200 border border-rose-500/40 font-bold text-[11px] disabled:opacity-40"
                  >
                    {own ? 'Withdraw' : 'Reject'}
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
};
