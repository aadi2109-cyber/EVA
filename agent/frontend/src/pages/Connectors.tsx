import React, { useState } from 'react';
import { ConnectorInfo } from '../api/types';

export const Connectors: React.FC = () => {
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([
    {
      id: 'gmail',
      name: 'Google Gmail (Inbound & Outbound)',
      status: 'connected',
      mode: 'mock',
      account: 'eva.agent.enclave@corp.internal',
      scopes: [
        'Read email headers and message snippets',
        'Create email drafts',
        'Send emails (strictly requires human approval)',
      ],
      expires_hint: 'Testing-mode token (refreshes via mock provider)',
    },
    {
      id: 'files',
      name: 'Sandboxed Workspace Filesystem',
      status: 'connected',
      mode: 'real',
      account: 'sandbox://genesis-eva/workspace',
      scopes: [
        'Read files in workspace directory',
        'Search file contents within scope',
        'Write files (requires approval outside scratch)',
      ],
      expires_hint: 'Persistent local mount',
    },
    {
      id: 'messages',
      name: 'Internal Enterprise Messaging',
      status: 'connected',
      mode: 'mock',
      account: '#general-enclave-feed',
      scopes: [
        'Read conversation threads',
        'Send channel broadcasts (mock channel only, requires approval)',
      ],
      expires_hint: 'Internal mock socket',
    },
  ]);

  const toggleGmailConnection = () => {
    setConnectors((prev) =>
      prev.map((c) => {
        if (c.id === 'gmail') {
          const nextStatus =
            c.status === 'connected' ? 'disconnected' : 'connected';
          return { ...c, status: nextStatus };
        }
        return c;
      })
    );
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <section className="bg-surface-container-low/90 backdrop-blur-xl p-5 rounded-2xl border border-white/10 shadow-xl flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary-container/15 border border-primary-container/40 text-primary-container flex items-center justify-center">
            <span className="material-symbols-outlined text-[24px]">hub</span>
          </div>
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight">
              External Enclave Connectors
            </h1>
            <p className="text-xs text-on-surface-variant">
              Every data retrieval from external connectors is treated as UNTRUSTED and routed through Tier-2 Sanitization.
            </p>
          </div>
        </div>
      </section>

      {/* Connectors List */}
      <div className="space-y-4">
        {connectors.map((connector) => {
          const isConnected = connector.status === 'connected';
          const isReconnect = connector.status === 'reconnect_needed';

          return (
            <div
              key={connector.id}
              className="p-5 sm:p-6 rounded-2xl bg-surface-container-low border border-white/5 shadow-xl flex flex-col md:flex-row md:items-start justify-between gap-5"
            >
              <div className="space-y-3 flex-1">
                <div className="flex items-center gap-3 flex-wrap">
                  <div className="w-9 h-9 rounded-xl bg-surface-container-high border border-white/10 flex items-center justify-center text-primary-container">
                    <span className="material-symbols-outlined text-[20px]">
                      {connector.id === 'gmail'
                        ? 'mail'
                        : connector.id === 'files'
                        ? 'folder_open'
                        : 'chat'}
                    </span>
                  </div>
                  <div>
                    <h3 className="font-bold text-white text-base">
                      {connector.name}
                    </h3>
                    <div className="flex items-center gap-2 font-mono text-xs text-on-surface-variant mt-0.5">
                      <span className="text-white">{connector.account}</span>
                      <span>·</span>
                      <span className="px-1.5 py-0.2 rounded bg-surface-container-high text-outline text-[10px] uppercase font-bold">
                        Mode: {connector.mode}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Plain Words Scopes */}
                <div className="space-y-1.5">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-outline block">
                    Permissions & Plain-Words Scopes
                  </span>
                  <div className="space-y-1">
                    {connector.scopes.map((scope, idx) => (
                      <div
                        key={idx}
                        className="flex items-center gap-2 text-xs text-on-surface-variant"
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-primary-container" />
                        <span>{scope}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {connector.expires_hint && (
                  <p className="text-[11px] font-mono text-outline">
                    Token Expiry Hint: {connector.expires_hint}
                  </p>
                )}
              </div>

              {/* Status & Action */}
              <div className="flex flex-col items-start md:items-end justify-between self-stretch gap-4">
                <span
                  className={`px-3 py-1 rounded-full font-mono text-xs font-bold border flex items-center gap-1.5 ${
                    isConnected
                      ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                      : isReconnect
                      ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                      : 'bg-surface-container-high text-outline border-white/10'
                  }`}
                >
                  <span
                    className={`w-2 h-2 rounded-full ${
                      isConnected
                        ? 'bg-emerald-400 animate-pulse'
                        : isReconnect
                        ? 'bg-amber-400'
                        : 'bg-outline'
                    }`}
                  />
                  {connector.status.toUpperCase()}
                </span>

                {connector.id === 'gmail' && (
                  <button
                    onClick={toggleGmailConnection}
                    className={`px-4 py-2 rounded-xl text-xs font-bold transition-all border ${
                      isConnected
                        ? 'bg-surface-container-high hover:bg-rose-500/20 text-white hover:text-rose-300 border-white/10 hover:border-rose-500/40'
                        : 'bg-primary-container text-on-primary-container shadow-[0_0_15px_rgba(200,243,34,0.3)]'
                    }`}
                  >
                    {isConnected ? 'Disconnect Account' : 'Connect Account'}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
