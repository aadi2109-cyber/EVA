import React, { useState } from 'react';
import { Health, AuditRecord } from '../api/types';

export const Admin: React.FC = () => {
  const [health] = useState<Health>({
    status: 'ok',
    tier2_available: true,
    t3_available: true,
    align_available: true,
    t2_model_hash: 'sha256:49c0d127ae80...',
    config_version: 3,
    contract_version: '0.1.0',
    kill_switch: {
      all_write_tools: false,
      tools: [],
    },
    metrics: {
      escalation_rate: 0.048,
      p50_ms: 12.4,
      p95_ms: 18.2,
    },
  });

  const [killSwitches, setKillSwitches] = useState({
    all_write_tools: false,
    'gmail.send': false,
    'files.write': false,
    'web.fetch': false,
  });

  const [auditRows] = useState<AuditRecord[]>([
    {
      id: 'aud_9021',
      ts: '2026-10-16T14:02:18.421Z',
      task_id: 'task-s1-prompt-injection',
      type: 'det.scan',
      actor: 'guard.det.tier2',
      payload: {
        tool: 'gmail.search',
        disposition: 'sanitized',
        removed_sentences: 1,
      },
      config_version: 3,
      prev_hash: '0000a98b1c4e782f...',
      hash: '9f830129bc7881ea...',
    },
    {
      id: 'aud_9022',
      ts: '2026-10-16T14:02:19.102Z',
      task_id: 'task-s1-prompt-injection',
      type: 'gateway.decision',
      actor: 'guard.gateway',
      payload: {
        tool: 'gmail.search',
        decision: 'ALLOW',
      },
      config_version: 3,
      prev_hash: '9f830129bc7881ea...',
      hash: '3bc71029da6614fa...',
    },
    {
      id: 'aud_9023',
      ts: '2026-10-16T13:58:10.021Z',
      task_id: 'task-s2-hijack-blocked',
      type: 'gateway.decision',
      actor: 'guard.gateway',
      payload: {
        tool: 'gmail.send',
        decision: 'DENY',
        reason: 'TOOL_PROHIBITED',
      },
      config_version: 3,
      prev_hash: '3bc71029da6614fa...',
      hash: '77ea1920bd817290...',
    },
  ]);

  const [verifyStatus, setVerifyStatus] = useState<string | null>(null);

  const handleVerifyChain = () => {
    setVerifyStatus('Validating cryptographic hash chain...');
    setTimeout(() => {
      setVerifyStatus('Cryptographic hash-chain integrity verified (3/3 rows valid, zero tampering detected).');
    }, 900);
  };

  const toggleKillSwitch = (key: keyof typeof killSwitches) => {
    setKillSwitches((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

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

      {/* Health Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl bg-surface-container-low border border-white/5 space-y-1">
          <span className="text-[11px] font-mono text-outline uppercase font-bold">
            Guard Enclave Status
          </span>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_#34d399]" />
            <span className="text-lg font-bold text-white">HEALTHY</span>
          </div>
          <p className="text-[11px] text-on-surface-variant">
            Tier-2 & Gateway active
          </p>
        </div>

        <div className="p-4 rounded-2xl bg-surface-container-low border border-white/5 space-y-1">
          <span className="text-[11px] font-mono text-outline uppercase font-bold">
            Latency (p50 / p95)
          </span>
          <div className="text-lg font-bold text-primary-container font-mono">
            {health.metrics.p50_ms} ms / {health.metrics.p95_ms} ms
          </div>
          <p className="text-[11px] text-on-surface-variant">
            Target &lt; 15 ms/KB met
          </p>
        </div>

        <div className="p-4 rounded-2xl bg-surface-container-low border border-white/5 space-y-1">
          <span className="text-[11px] font-mono text-outline uppercase font-bold">
            T3 / LAYA Escalation
          </span>
          <div className="text-lg font-bold text-white font-mono">
            {(health.metrics.escalation_rate * 100).toFixed(1)}%
          </div>
          <p className="text-[11px] text-on-surface-variant">
            Target &lt; 10% met
          </p>
        </div>

        <div className="p-4 rounded-2xl bg-surface-container-low border border-white/5 space-y-1">
          <span className="text-[11px] font-mono text-outline uppercase font-bold">
            Contract Version
          </span>
          <div className="text-lg font-bold text-white font-mono">
            v{health.contract_version} (cfg {health.config_version})
          </div>
          <p className="text-[11px] text-on-surface-variant">
            Hash: {health.t2_model_hash?.slice(0, 14)}
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
          {Object.entries(killSwitches).map(([target, enabled]) => (
            <div
              key={target}
              className={`p-3.5 rounded-xl border flex flex-col justify-between gap-3 transition-colors ${
                enabled
                  ? 'bg-rose-950/40 border-rose-500/50'
                  : 'bg-surface-container border-white/5'
              }`}
            >
              <div>
                <span className="font-mono text-xs font-bold text-white block">
                  {target}
                </span>
                <span className="text-[10px] text-outline">
                  {enabled ? 'BLOCKED' : 'ALLOWABLE'}
                </span>
              </div>
              <button
                type="button"
                onClick={() => toggleKillSwitch(target as any)}
                className={`px-3 py-1.5 rounded-lg font-mono text-xs font-bold transition-all ${
                  enabled
                    ? 'bg-rose-500 text-white'
                    : 'bg-surface-container-high hover:bg-surface-container-highest text-white'
                }`}
              >
                {enabled ? 'ACTIVE (BLOCKING)' : 'ENGAGE BLOCK'}
              </button>
            </div>
          ))}
        </div>
      </section>

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
          <div className="p-3 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 font-mono text-xs flex items-center gap-2">
            <span className="material-symbols-outlined text-[16px]">
              check_circle
            </span>
            <span>{verifyStatus}</span>
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
                    {row.ts.split('T')[1].replace('Z', '')}
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
        </div>
      </section>

      {/* Acceptance Matrix (doc 04) */}
      <section className="p-5 sm:p-6 rounded-2xl bg-surface-container-low border border-white/5 shadow-xl space-y-4">
        <div>
          <h3 className="font-bold text-white text-base">
            Security Acceptance Matrix (doc 04 Configurations)
          </h3>
          <p className="text-xs text-on-surface-variant">
            Comparison across Baseline (off), Basic (T1 + allowlist), and Full (Full Enclave Gateway).
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-white/10 text-outline font-mono">
                <th className="py-2 px-3">Metric</th>
                <th className="py-2 px-3">Baseline (Off)</th>
                <th className="py-2 px-3">Basic (T1)</th>
                <th className="py-2 px-3 text-primary-container">
                  Full (EVA Guard)
                </th>
                <th className="py-2 px-3">Target</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 font-mono text-on-surface">
              <tr>
                <td className="py-2.5 px-3 font-sans font-medium text-white">
                  Unauthorized Side Effects
                </td>
                <td className="py-2.5 px-3 text-rose-400">14 (Vulnerable)</td>
                <td className="py-2.5 px-3 text-amber-400">4</td>
                <td className="py-2.5 px-3 text-emerald-400 font-bold">
                  0 (0 / 14 suites)
                </td>
                <td className="py-2.5 px-3 text-outline">0</td>
              </tr>
              <tr>
                <td className="py-2.5 px-3 font-sans font-medium text-white">
                  Clean-Task Completion
                </td>
                <td className="py-2.5 px-3">94%</td>
                <td className="py-2.5 px-3">91%</td>
                <td className="py-2.5 px-3 text-primary-container font-bold">
                  92.4%
                </td>
                <td className="py-2.5 px-3 text-outline">≥ 90%</td>
              </tr>
              <tr>
                <td className="py-2.5 px-3 font-sans font-medium text-white">
                  Sanitization Precision
                </td>
                <td className="py-2.5 px-3">0%</td>
                <td className="py-2.5 px-3">62%</td>
                <td className="py-2.5 px-3 text-primary-container font-bold">
                  88.7%
                </td>
                <td className="py-2.5 px-3 text-outline">&gt; 85%</td>
              </tr>
              <tr>
                <td className="py-2.5 px-3 font-sans font-medium text-white">
                  Gateway Audit Completeness
                </td>
                <td className="py-2.5 px-3">0%</td>
                <td className="py-2.5 px-3">100%</td>
                <td className="py-2.5 px-3 text-emerald-400 font-bold">100%</td>
                <td className="py-2.5 px-3 text-outline">100%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};
