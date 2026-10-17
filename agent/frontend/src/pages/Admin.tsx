import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Health, AuditRecord, EvalRunSummary, EvalSummary, User } from '../api/types';
import { ReviewQueue } from '../components/admin/ReviewQueue';
import { ConfigProposals } from '../components/admin/ConfigProposals';

const KILL_TARGETS: { key: string; scope: 'tool' | 'all_write_tools'; label: string }[] = [
  { key: 'all_write_tools', scope: 'all_write_tools', label: 'all_write_tools' },
  { key: 'gmail.send', scope: 'tool', label: 'gmail.send' },
  { key: 'files.write', scope: 'tool', label: 'files.write' },
  { key: 'messages.send', scope: 'tool', label: 'messages.send' },
];

interface AdminProps {
  currentUser: User;
}

export const Admin: React.FC<AdminProps> = ({ currentUser }) => {
  const [health, setHealth] = useState<Health | null>(null);
  const [auditRows, setAuditRows] = useState<AuditRecord[]>([]);
  const [evalRuns, setEvalRuns] = useState<EvalRunSummary[] | null>(null);
  const [evalSummary, setEvalSummary] = useState<EvalSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verifyStatus, setVerifyStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const loadHealth = () =>
    api.admin
      .getHealth()
      .then(setHealth)
      .catch((e) => setError(e?.message || 'Failed to load guard health'));

  useEffect(() => {
    void loadHealth();
    api.admin
      .getAudit()
      .then(setAuditRows)
      .catch((e) => setError(e?.message || 'Failed to load audit log'));
    api.admin
      .getEvalRuns()
      .then(setEvalRuns)
      .catch(() => setEvalRuns(null));
    api.admin
      .getEvalSummary()
      .then(setEvalSummary)
      .catch(() => setEvalSummary(null));
  }, []);

  const killState = (key: string): boolean => {
    const ks: any = health?.kill_switch;
    if (!ks) return false;
    return key === 'all_write_tools' ? !!ks.all_write_tools : (ks.tools || []).includes(key);
  };

  const handleVerifyChain = async () => {
    setVerifyStatus({ ok: true, text: 'Validating hash chain…' });
    try {
      const r = await api.admin.verifyAudit();
      setVerifyStatus({ ok: r.valid, text: `${r.message} (${r.chain_length} rows${r.tampered_event_id ? `, tampered: ${r.tampered_event_id}` : ''})` });
    } catch (e: any) {
      setVerifyStatus({ ok: false, text: e?.message || 'Verification failed' });
    }
  };

  const toggleKillSwitch = async (t: (typeof KILL_TARGETS)[number]) => {
    setBusy(true);
    try {
      setHealth(
        await api.admin.setKillSwitch(t.scope, t.scope === 'all_write_tools' ? null : t.key, !killState(t.key))
      );
    } catch (e: any) {
      setError(e?.message || 'Kill switch change failed');
    } finally {
      setBusy(false);
    }
  };

  const m = (health?.metrics || {}) as Record<string, number>;
  const fmt = (v: number | undefined, unit = '') => (typeof v === 'number' ? `${v}${unit}` : '—');

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <section className="bg-surface-container-low/90 backdrop-blur-xl p-5 rounded-2xl border border-white/10 shadow-xl flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary-container/15 border border-primary-container/40 text-primary-container flex items-center justify-center">
            <span className="material-symbols-outlined text-[24px]">security</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-white tracking-tight">
                Admin Security Operations & Audit Enclave
              </h1>
              <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
                ADMIN AUTHORIZED
              </span>
            </div>
            <p className="text-xs text-on-surface-variant">
              System health, immutable audit chain explorer, kill-switch authority, and evaluation acceptance matrix.
            </p>
          </div>
        </div>
      </section>

      {error && (
        <div role="alert" className="text-xs text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-xl px-4 py-2">
          {error}
        </div>
      )}

      {/* Health Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl bg-surface-container-low border border-white/5 space-y-1">
          <span className="text-[11px] font-mono text-outline uppercase font-bold">
            Guard Enclave Status
          </span>
          <div className="flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${health?.status === 'ok' ? 'bg-emerald-400' : 'bg-orange-400'}`} />
            <span className="text-lg font-bold text-white">{health ? health.status.toUpperCase() : '…'}</span>
          </div>
          <p className="text-[11px] text-on-surface-variant">
            Tier-2: {health?.tier2_available ? 'up' : 'down'} · T3: {health?.t3_available ? 'up' : 'down'} · ALIGN: {health?.align_available ? 'up' : 'down'}
          </p>
        </div>

        <div className="p-4 rounded-2xl bg-surface-container-low border border-white/5 space-y-1">
          <span className="text-[11px] font-mono text-outline uppercase font-bold">
            Latency (p50 / p95)
          </span>
          <div className="text-lg font-bold text-primary-container font-mono">
            {fmt(m.p50_ms, ' ms')} / {fmt(m.p95_ms, ' ms')}
          </div>

        </div>

        <div className="p-4 rounded-2xl bg-surface-container-low border border-white/5 space-y-1">
          <span className="text-[11px] font-mono text-outline uppercase font-bold">
            T3 / LAYA Escalation
          </span>
          <div className="text-lg font-bold text-white font-mono">
            {typeof m.escalation_rate === 'number' ? `${(m.escalation_rate * 100).toFixed(1)}%` : '—'}
          </div>

        </div>

        <div className="p-4 rounded-2xl bg-surface-container-low border border-white/5 space-y-1">
          <span className="text-[11px] font-mono text-outline uppercase font-bold">
            Contract Version
          </span>
          <div className="text-lg font-bold text-white font-mono">
            {health ? `v${health.contract_version} (cfg ${health.config_version})` : '…'}
          </div>
          <p className="text-[11px] text-on-surface-variant">
            Hash: {health?.t2_model_hash?.slice(0, 14) ?? '—'}
          </p>
        </div>
      </div>

      {/* Kill Switch Controls */}
      <section className="p-5 sm:p-6 rounded-2xl bg-surface-container-low border border-white/5 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-white/5 pb-3">
          <div>
            <h3 className="font-bold text-white text-base">
              Emergency Kill-Switch Matrix
            </h3>
            <p className="text-xs text-on-surface-variant">
              Instantly revokes gateway authority. Lowering policy floor requires second admin approval.
            </p>
          </div>
          <span className="text-[10px] font-mono text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/30 font-bold">
            HIGH AUTHORITY
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          {KILL_TARGETS.map((t) => {
            const enabled = killState(t.key);
            return (
              <div
                key={t.key}
                className={`p-3.5 rounded-xl border flex flex-col justify-between gap-3 transition-colors ${
                  enabled ? 'bg-rose-950/40 border-rose-500/50' : 'bg-surface-container border-white/5'
                }`}
              >
                <div>
                  <span className="font-mono text-xs font-bold text-white block">{t.label}</span>
                  <span className="text-[10px] text-outline">{enabled ? 'BLOCKED' : 'ALLOWABLE'}</span>
                </div>
                <button
                  type="button"
                  disabled={busy || !health}
                  onClick={() => toggleKillSwitch(t)}
                  className={`px-3 py-1.5 rounded-lg font-mono text-xs font-bold transition-all ${
                    enabled ? 'bg-rose-500 text-white' : 'bg-surface-container-high hover:bg-surface-container-highest text-white'
                  }`}
                >
                  {enabled ? 'ACTIVE (CLICK TO RELEASE)' : 'ENGAGE BLOCK'}
                </button>
              </div>
            );
          })}
        </div>
      </section>

      <ConfigProposals currentAdminId={currentUser.id} />

      <ReviewQueue reviewerId={currentUser.id} />

      {/* Audit Explorer */}
      <section className="p-5 sm:p-6 rounded-2xl bg-surface-container-low border border-white/5 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/5 pb-3">
          <div>
            <h3 className="font-bold text-white text-base">
              Cryptographic Audit Log Explorer
            </h3>
            <p className="text-xs text-on-surface-variant">
              Every gateway decision and scan verdict is linked in an immutable SHA-256 hash chain.
            </p>
          </div>
          <button
            type="button"
            onClick={handleVerifyChain}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary-container text-on-primary-container font-bold text-xs shadow-md transition-all self-start sm:self-auto"
          >
            <span className="material-symbols-outlined text-[16px]">
              verified
            </span>
            <span>Verify Hash Chain</span>
          </button>
        </div>

        {verifyStatus && (
          <div className={`p-3 rounded-xl border font-mono text-xs flex items-center gap-2 ${verifyStatus.ok ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300' : 'bg-rose-500/15 border-rose-500/30 text-rose-300'}`}>
            <span className="material-symbols-outlined text-[16px]">
              {verifyStatus.ok ? 'check_circle' : 'error'}
            </span>
            <span>{verifyStatus.text}</span>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-white/10 text-outline">
                <th className="py-2 px-3">Event ID</th>
                <th className="py-2 px-3">Timestamp</th>
                <th className="py-2 px-3">Task ID</th>
                <th className="py-2 px-3">Type</th>
                <th className="py-2 px-3">Actor</th>
                <th className="py-2 px-3">Hash Link</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 text-on-surface">
              {auditRows.map((row) => (
                <tr key={row.id} className="hover:bg-surface-container/40">
                  <td className="py-2.5 px-3 text-primary-container font-bold">
                    {row.id}
                  </td>
                  <td className="py-2.5 px-3 text-outline">
                    {new Date(row.ts).toLocaleTimeString()}
                  </td>
                  <td className="py-2.5 px-3">{row.task_id}</td>
                  <td className="py-2.5 px-3">
                    <span className="px-2 py-0.5 rounded bg-surface-container-high text-white">
                      {row.type}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-on-surface-variant">
                    {row.actor}
                  </td>
                  <td className="py-2.5 px-3 text-outline">
                    {row.hash.slice(0, 12)}...
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {auditRows.length === 0 && (
            <p className="text-xs font-mono text-outline py-3">No audit events yet.</p>
          )}
        </div>
      </section>

      {/* Eval runs (read-only, from the guard) */}
      <section className="p-5 sm:p-6 rounded-2xl bg-surface-container-low border border-white/5 shadow-xl space-y-3">
        <h3 className="font-bold text-white text-base">Evaluation Runs</h3>
        {evalRuns === null ? (
          <p className="text-xs font-mono text-outline">Eval runs could not be loaded.</p>
        ) : evalRuns.length === 0 ? (
          <p className="text-xs font-mono text-outline">No eval runs recorded.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-white/10 text-outline">
                  <th className="py-2 px-3">Run</th>
                  <th className="py-2 px-3">Kind</th>
                  <th className="py-2 px-3">Time</th>
                  <th className="py-2 px-3">Cases</th>
                  <th className="py-2 px-3">Failed</th>
                  <th className="py-2 px-3">Commit</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-on-surface">
                {evalRuns.map((r) => (
                  <tr key={r.id}>
                    <td className="py-2 px-3 text-primary-container">{r.id}</td>
                    <td className="py-2 px-3">{r.kind}</td>
                    <td className="py-2 px-3 text-outline">{new Date(r.created_at).toLocaleString()}</td>
                    <td className="py-2 px-3">{r.n}</td>
                    <td className={`py-2 px-3 ${r.failed_count > 0 ? 'text-rose-300' : 'text-emerald-300'}`}>{r.failed_count}</td>
                    <td className="py-2 px-3 text-outline">{r.git_sha ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {evalSummary?.comparison_table && evalSummary.comparison_table.length > 0 && (
          <div className="overflow-x-auto pt-2">
            <table className="w-full text-left text-xs font-mono" aria-label="Baseline, Basic and Full comparison">
              <thead>
                <tr className="border-b border-white/10 text-outline">
                  <th className="py-2 px-3">Metric</th>
                  <th className="py-2 px-3">Baseline (off)</th>
                  <th className="py-2 px-3">Basic</th>
                  <th className="py-2 px-3 text-primary-container">Full</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-on-surface">
                {evalSummary.comparison_table.map((row) => (
                  <tr key={row.metric}>
                    <td className="py-2 px-3 font-sans text-white">{row.metric.replace(/_/g, ' ')}</td>
                    {(['baseline', 'basic', 'full'] as const).map((k) => (
                      <td key={k} className="py-2 px-3">{row[k] ?? '—'}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {evalSummary?.notes?.map((n) => (
          <p key={n} className="text-[11px] text-outline">{n}</p>
        ))}
      </section>
    </div>
  );
};
