import React, { useState } from 'react';
import { LiveTracePanel } from '../components/LiveTracePanel';
import { SecurityTraceItem, User } from '../api/types';

interface SettingsTraceProps {
  traceItems: SecurityTraceItem[];
  currentUser: User;
}

export const SettingsTrace: React.FC<SettingsTraceProps> = ({
  traceItems,
  currentUser,
}) => {
  const [activePillar, setActivePillar] = useState<string>('profile');
  const [isTraceVisible, setIsTraceVisible] = useState<boolean>(true);
  const [notification, setNotification] = useState<string | null>(null);

  const handleEnforcePolicy = () => {
    setNotification('Policy state re-attested across all enclaves.');
    setTimeout(() => setNotification(null), 3000);
  };

  return (
    <div className="space-y-6">
      {/* Notification Toast */}
      {notification && (
        <div className="fixed bottom-6 right-6 z-50 bg-primary-container text-on-primary-container px-4 py-2.5 rounded-xl font-bold text-xs shadow-2xl flex items-center gap-2 animate-in fade-in slide-in-from-bottom-3">
          <span className="material-symbols-outlined text-[16px]">check_circle</span>
          <span>{notification}</span>
        </div>
      )}

      {/* Top Action Header with LIVE TRACE TOGGLE BUTTON */}
      <section className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-surface-container-low/90 backdrop-blur-xl p-4 sm:p-5 rounded-2xl shadow-xl border border-white/10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary-container/15 border border-primary-container/40 text-primary-container flex items-center justify-center shadow-[0_0_16px_rgba(200,243,34,0.25)]">
            <span className="material-symbols-outlined text-[24px]">terminal</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg sm:text-xl font-bold text-white tracking-tight">
                Security Telemetry & Live Trace Hub
              </h1>
              <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                FIPS 140-3 LIVE
              </span>
            </div>
            <p className="text-xs sm:text-sm text-on-surface-variant">
              Real-time prompt firewall, zero-shot quarantine, and enclave audit stream.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Live Security Trace Toggle Button */}
          <button
            id="toggle-trace-btn"
            type="button"
            onClick={() => setIsTraceVisible(!isTraceVisible)}
            className="flex items-center gap-2.5 px-4 py-2 rounded-full bg-surface-container-high hover:bg-surface-container-highest border border-primary-container/40 hover:border-primary-container text-white text-xs sm:text-sm font-semibold transition-all shadow-[0_0_18px_rgba(200,243,34,0.18)] group"
          >
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-container opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-primary-container shadow-[0_0_6px_#c8f322]"></span>
            </span>
            <span className="font-bold text-primary-container">Live Security Trace</span>
            <span className="font-mono text-[11px] px-2 py-0.5 rounded-full bg-surface-container-lowest text-white border border-white/10">
              {traceItems.length} Events
            </span>
            <span
              className={`material-symbols-outlined text-[18px] text-on-surface-variant group-hover:translate-y-0.5 transition-transform ${
                isTraceVisible ? 'rotate-180' : ''
              }`}
            >
              expand_more
            </span>
          </button>

          <button
            type="button"
            className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-surface-container hover:bg-surface-container-high text-xs sm:text-sm font-semibold border border-white/10 transition-colors text-white"
          >
            <span
              className="material-symbols-outlined text-[16px] text-primary-container animate-spin"
              style={{ animationDuration: '4s' }}
            >
              sync
            </span>
            <span>Enclave Synced</span>
          </button>

          <button
            type="button"
            onClick={handleEnforcePolicy}
            className="flex items-center gap-2 px-5 py-2 rounded-full bg-primary-container text-on-primary-container text-xs sm:text-sm font-bold shadow-[0_0_20px_rgba(200,243,34,0.35)] hover:shadow-[0_0_28px_rgba(200,243,34,0.6)] hover:scale-[1.02] active:scale-[0.98] transition-all"
          >
            <span className="material-symbols-outlined text-[18px]">
              verified_user
            </span>
            <span>Enforce Policies</span>
          </button>
        </div>
      </section>

      {/* LIVE SECURITY TRACE PANEL */}
      {isTraceVisible && (
        <LiveTracePanel
          items={traceItems}
          isEmbedded={true}
          onClose={() => setIsTraceVisible(false)}
        />
      )}

      {/* Settings Split Section */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Settings Navigation Pillars */}
        <aside className="lg:col-span-3 flex flex-col gap-1.5 bg-surface-container-low/90 backdrop-blur-xl p-3 rounded-2xl shadow-xl sticky top-20 border border-white/5">
          <div className="px-3 py-1 mb-1">
            <span className="text-[11px] font-bold uppercase tracking-wider text-outline-variant">
              Navigation Pillars
            </span>
          </div>

          <button
            onClick={() => setActivePillar('profile')}
            className={`w-full text-left flex items-center justify-between p-3 rounded-xl transition-all group ${
              activePillar === 'profile'
                ? 'bg-surface-container-high shadow-[0_0_16px_rgba(200,243,34,0.15)] border border-primary-container/30'
                : 'hover:bg-surface-container'
            }`}
            type="button"
          >
            <div className="flex items-center gap-3 min-w-0">
              <span
                className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                  activePillar === 'profile'
                    ? 'bg-primary-container text-on-primary-container'
                    : 'bg-surface-container-high text-on-surface-variant'
                }`}
              >
                <span className="material-symbols-outlined text-[18px]">
                  badge
                </span>
              </span>
              <div className="flex flex-col min-w-0">
                <span className="text-xs font-bold text-white truncate">
                  Profile & Identity
                </span>
                <span className="text-[11px] text-on-surface-variant truncate">
                  Apex Enclave Lead
                </span>
              </div>
            </div>
            {activePillar === 'profile' && (
              <span className="w-2 h-2 rounded-full bg-primary-container shadow-[0_0_8px_#c8f322]"></span>
            )}
          </button>

          <button
            onClick={() => setActivePillar('security')}
            className={`w-full text-left flex items-center justify-between p-3 rounded-xl transition-colors group ${
              activePillar === 'security'
                ? 'bg-surface-container-high shadow-[0_0_16px_rgba(200,243,34,0.15)] border border-primary-container/30'
                : 'hover:bg-surface-container'
            }`}
            type="button"
          >
            <div className="flex items-center gap-3 min-w-0">
              <span
                className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                  activePillar === 'security'
                    ? 'bg-primary-container text-on-primary-container'
                    : 'bg-surface-container-high text-on-surface-variant'
                }`}
              >
                <span className="material-symbols-outlined text-[18px]">
                  shield_lock
                </span>
              </span>
              <div className="flex flex-col min-w-0">
                <span className="text-xs font-medium text-white truncate">
                  Security & Enclaves
                </span>
                <span className="text-[11px] text-outline truncate">
                  FIPS 140-3 & 2FA
                </span>
              </div>
            </div>
            <span className="material-symbols-outlined text-outline text-[16px]">
              chevron_right
            </span>
          </button>

          <button
            onClick={() => setActivePillar('credit')}
            className={`w-full text-left flex items-center justify-between p-3 rounded-xl transition-colors group ${
              activePillar === 'credit'
                ? 'bg-surface-container-high shadow-[0_0_16px_rgba(200,243,34,0.15)] border border-primary-container/30'
                : 'hover:bg-surface-container'
            }`}
            type="button"
          >
            <div className="flex items-center gap-3 min-w-0">
              <span
                className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                  activePillar === 'credit'
                    ? 'bg-primary-container text-on-primary-container'
                    : 'bg-surface-container-high text-on-surface-variant'
                }`}
              >
                <span className="material-symbols-outlined text-[18px]">
                  toll
                </span>
              </span>
              <div className="flex flex-col min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-white truncate">
                    Credit & Tokens
                  </span>
                  <span className="text-[10px] font-bold px-1.5 py-0.2 rounded-full bg-secondary-container text-on-secondary-container">
                    ₹1,420
                  </span>
                </div>
                <span className="text-[11px] text-outline truncate">
                  MiniMoth OTP pool
                </span>
              </div>
            </div>
            <span className="material-symbols-outlined text-outline text-[16px]">
              chevron_right
            </span>
          </button>

          <button
            onClick={() => setActivePillar('audit')}
            className={`w-full text-left flex items-center justify-between p-3 rounded-xl transition-colors group ${
              activePillar === 'audit'
                ? 'bg-surface-container-high shadow-[0_0_16px_rgba(200,243,34,0.15)] border border-primary-container/30'
                : 'hover:bg-surface-container'
            }`}
            type="button"
          >
            <div className="flex items-center gap-3 min-w-0">
              <span
                className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                  activePillar === 'audit'
                    ? 'bg-primary-container text-on-primary-container'
                    : 'bg-surface-container-high text-on-surface-variant'
                }`}
              >
                <span className="material-symbols-outlined text-[18px]">
                  receipt_long
                </span>
              </span>
              <div className="flex flex-col min-w-0">
                <span className="text-xs font-medium text-white truncate">
                  Audit Logs & SOC-2
                </span>
                <span className="text-[11px] text-outline truncate">
                  Tamper-proof telemetry
                </span>
              </div>
            </div>
            <span className="material-symbols-outlined text-outline text-[16px]">
              chevron_right
            </span>
          </button>
        </aside>

        {/* Right Settings Content Panel */}
        <div className="lg:col-span-9 flex flex-col gap-6">
          {/* Profile Card */}
          <section className="rounded-2xl bg-surface-container-low p-5 sm:p-6 shadow-xl border border-white/5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="relative shrink-0">
                <div className="w-16 h-16 rounded-2xl bg-surface-container-high ring-2 ring-primary-container/40 flex items-center justify-center text-xl font-bold text-white border border-white/10">
                  {currentUser.name
                    .split(' ')
                    .map((n) => n[0])
                    .join('')}
                </div>
                <span className="absolute -bottom-1 -right-1 bg-surface-container-lowest p-0.5 rounded-full text-primary-container">
                  <span className="material-symbols-outlined text-[16px] bg-surface-container-high rounded-full p-0.5">
                    verified_user
                  </span>
                </span>
              </div>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="text-lg font-bold text-white">
                    {currentUser.name}
                  </h2>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-primary-container/20 text-primary-container border border-primary-container/30 uppercase">
                    Security Operations Lead
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-on-surface-variant mt-1 flex-wrap">
                  <span className="font-mono">{currentUser.email}</span>
                  <span>·</span>
                  <span className="font-mono text-outline">
                    ID: {currentUser.id}
                  </span>
                  <span>·</span>
                  <span className="text-emerald-400 font-semibold flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                    Enclave Keypair Attested
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 font-mono text-xs">
              <span className="px-3 py-1.5 rounded-xl bg-surface-container-high border border-white/10 text-white">
                FIPS Session: ACTIVE
              </span>
            </div>
          </section>

          {/* Enclave Security Controls Card */}
          <section className="rounded-2xl bg-surface-container-low p-5 sm:p-6 shadow-xl border border-white/5 space-y-4">
            <div className="flex items-center justify-between border-b border-white/5 pb-3">
              <div>
                <h3 className="font-bold text-white text-base">
                  Enclave Security Posture & Guard Configuration
                </h3>
                <p className="text-xs text-on-surface-variant">
                  Configured according to EVA Contract v0.1.0 specifications.
                </p>
              </div>
              <span className="font-mono text-xs text-primary-container px-2.5 py-1 rounded-full bg-primary-container/10 border border-primary-container/30 font-bold">
                ENFORCED
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              <div className="p-4 rounded-xl bg-surface-container-lowest/80 border border-white/5 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-white">
                    Deterministic Gateway
                  </span>
                  <span className="text-[10px] font-mono font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/30">
                    AUTHORITY
                  </span>
                </div>
                <p className="text-xs text-on-surface-variant">
                  All side-effect tool operations evaluate rules 1–11 before tool execution.
                </p>
              </div>

              <div className="p-4 rounded-xl bg-surface-container-lowest/80 border border-white/5 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-white">
                    Zero-Shot Ingress Quarantine
                  </span>
                  <span className="text-[10px] font-mono font-bold text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/30">
                    TIER-2 DEBERTA
                  </span>
                </div>
                <p className="text-xs text-on-surface-variant">
                  Inbound emails, files, and web responses are scanned; malicious sentences are stripped before model ingestion.
                </p>
              </div>

              <div className="p-4 rounded-xl bg-surface-container-lowest/80 border border-white/5 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-white">
                    Fail-Closed Posture Override
                  </span>
                  <span className="text-[10px] font-mono font-bold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/30">
                    FAIL_CLOSED
                  </span>
                </div>
                <p className="text-xs text-on-surface-variant">
                  If the Tier-2 neural detector experiences latency SLO breach, side-effect tools are halted immediately.
                </p>
              </div>

              <div className="p-4 rounded-xl bg-surface-container-lowest/80 border border-white/5 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-white">
                    Cryptographic Audit Chain
                  </span>
                  <span className="text-[10px] font-mono font-bold text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded border border-purple-500/30">
                    SHA-256 HASH CHAIN
                  </span>
                </div>
                <p className="text-xs text-on-surface-variant">
                  Every scan, gateway decision, and state verification is immutably signed and verifiable by auditors.
                </p>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};
