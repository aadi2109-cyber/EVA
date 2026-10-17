import React, { useEffect, useState } from 'react';
import { ConnectorInfo } from '../api/types';
import { api } from '../api/client';

const STATIC_CONNECTORS: ConnectorInfo[] = [
  {
    id: 'files',
    name: 'Sandboxed Workspace Filesystem',
    status: 'connected',
    mode: 'real',
    account: 'workspace',
    scopes: ['Read files in the workspace', 'Write files (requires approval outside scratch)'],
    expires_hint: 'Local mount, no token',
  },
  {
    id: 'messages',
    name: 'Messages',
    status: 'connected',
    mode: 'mock',
    account: 'mock channel',
    scopes: ['Send channel messages (mock channel only, always requires approval)'],
    expires_hint: 'Mock, no token',
  },
];

export const Connectors: React.FC = () => {
  const [serverConnectors, setServerConnectors] = useState<ConnectorInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Telegram link code modal / flow state
  const [linkModalOpen, setLinkModalOpen] = useState(false);
  const [linkCodeData, setLinkCodeData] = useState<{
    code: string;
    expires_at: string;
    instructions: string;
  } | null>(null);
  const [verifyChatId, setVerifyChatId] = useState('');
  const [verifyStatus, setVerifyStatus] = useState<string | null>(null);

  const load = async () => {
    try {
      setServerConnectors(await api.connectors.list());
      setError(null);
    } catch (e: any) {
      setError(e?.message || 'Failed to load connectors');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  // Merge server-reported connectors (Gmail, Telegram) with static demo ones (Files, Messages)
  const connectors = [...serverConnectors, ...STATIC_CONNECTORS.filter(
    (sc) => !serverConnectors.some((s) => s.id === sc.id)
  )];

  const toggleGmailConnection = async () => {
    const g = serverConnectors.find((c) => c.id === 'gmail');
    if (!g || g.mode === 'mock') return;
    setBusy(true);
    try {
      if (g.status === 'connected') {
        await api.connectors.disconnectGmail();
        await load();
      } else {
        const { url } = await api.connectors.getGmailAuthUrl();
        window.location.href = url;
      }
    } catch (e: any) {
      setError(e?.message || 'Connector action failed');
    } finally {
      setBusy(false);
    }
  };

  const handleOpenTelegramLink = async () => {
    setBusy(true);
    setVerifyStatus(null);
    try {
      const data = await api.connectors.getTelegramLinkCode();
      setLinkCodeData(data);
      setLinkModalOpen(true);
    } catch (e: any) {
      setError(e?.message || 'Failed to generate Telegram linking code');
    } finally {
      setBusy(false);
    }
  };

  const handleDisconnectTelegram = async () => {
    setBusy(true);
    try {
      await api.connectors.disconnectTelegram();
      await load();
    } catch (e: any) {
      setError(e?.message || 'Failed to disconnect Telegram');
    } finally {
      setBusy(false);
    }
  };

  const handleConfirmVerify = async () => {
    if (!linkCodeData || !verifyChatId.trim()) return;
    setBusy(true);
    try {
      await api.connectors.verifyTelegramLink({
        code: linkCodeData.code,
        chat_id: verifyChatId.trim(),
        chat_type: 'private',
      });
      setVerifyStatus('Successfully linked private chat!');
      await load();
      setTimeout(() => {
        setLinkModalOpen(false);
        setVerifyStatus(null);
        setVerifyChatId('');
      }, 1200);
    } catch (e: any) {
      setVerifyStatus(`Linking failed: ${e?.message || 'Unknown error'}`);
    } finally {
      setBusy(false);
    }
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

      {error && (
        <div role="alert" className="text-xs text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-xl px-4 py-2">
          {error}
        </div>
      )}
      {loading && <p className="text-xs font-mono text-outline">Loading connectors…</p>}

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
                        : connector.id === 'telegram'
                        ? 'send'
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
                      <span className="text-white">{connector.account || 'Not linked'}</span>
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
                    Note: {connector.expires_hint}
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

                {/* Gmail Connect Button */}
                {connector.id === 'gmail' && connector.mode === 'real' && (
                  <button
                    disabled={busy}
                    onClick={toggleGmailConnection}
                    className={`px-4 py-2 rounded-xl text-xs font-bold transition-all border ${
                      isConnected
                        ? 'bg-surface-container-high hover:bg-rose-500/20 text-white hover:text-rose-300 border-white/10 hover:border-rose-500/40'
                        : 'bg-primary-container text-on-primary-container shadow-[0_0_15px_rgba(200,243,34,0.3)]'
                    }`}
                  >
                    {isConnected ? 'Disconnect Account' : isReconnect ? 'Reconnect Account' : 'Connect Account'}
                  </button>
                )}

                {/* Telegram Connect / Link Actions */}
                {connector.id === 'telegram' && (
                  <div className="flex items-center gap-2">
                    {isConnected && (
                      <button
                        disabled={busy}
                        onClick={handleDisconnectTelegram}
                        className="px-4 py-2 rounded-xl text-xs font-bold transition-all border bg-surface-container-high hover:bg-rose-500/20 text-white hover:text-rose-300 border-white/10 hover:border-rose-500/40"
                      >
                        Unlink Chat
                      </button>
                    )}
                    <button
                      disabled={busy}
                      onClick={handleOpenTelegramLink}
                      className="px-4 py-2 rounded-xl text-xs font-bold transition-all bg-primary-container hover:bg-white text-on-primary-container shadow-[0_0_15px_rgba(200,243,34,0.3)]"
                    >
                      {isConnected ? 'Re-Link Chat Code' : 'Link Telegram Chat'}
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Link Verification Modal */}
      {linkModalOpen && linkCodeData && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
          <div className="w-full max-w-lg bg-surface-container-low border border-primary-container/40 rounded-2xl shadow-2xl p-6 space-y-5 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div className="flex items-center gap-2.5">
                <span className="material-symbols-outlined text-primary-container text-[22px]">
                  lock_open
                </span>
                <h3 className="font-bold text-white text-base">Link Telegram Chat</h3>
              </div>
              <button
                type="button"
                onClick={() => setLinkModalOpen(false)}
                className="text-on-surface-variant hover:text-white"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>

            <div className="space-y-3 text-xs text-on-surface">
              <p className="text-on-surface-variant leading-relaxed">
                To isolate private chats and prevent rogue access, EVA generates a single-use verification code:
              </p>

              <div className="p-4 rounded-xl bg-surface-container-lowest border border-primary-container/30 text-center space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wider text-outline block">
                  Single-Use Verification Code
                </span>
                <span className="font-mono text-2xl font-bold text-primary-container tracking-wider block selection:bg-primary-container selection:text-black">
                  {linkCodeData.code}
                </span>
                <span className="text-[10px] font-mono text-amber-300 block">
                  Expires: {new Date(linkCodeData.expires_at).toLocaleTimeString()}
                </span>
              </div>

              <div className="p-3 rounded-lg bg-surface-container border border-white/5 space-y-1 font-mono text-[11px]">
                <span className="text-outline font-bold block uppercase text-[9px]">Instructions:</span>
                <p className="text-white">{linkCodeData.instructions}</p>
              </div>

              {/* Direct Simulation / Mock Verification Input */}
              <div className="pt-2 space-y-2 border-t border-white/5">
                <label className="block text-[11px] font-bold text-outline uppercase">
                  Simulate or Confirm Telegram Chat ID
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={verifyChatId}
                    onChange={(e) => setVerifyChatId(e.target.value)}
                    placeholder="e.g. 12345678 or @my_telegram_handle"
                    className="flex-1 bg-surface-container-lowest border border-white/10 rounded-xl px-3 py-2 text-xs font-mono text-white focus:outline-none focus:ring-1 focus:ring-primary-container"
                  />
                  <button
                    type="button"
                    disabled={busy || !verifyChatId.trim()}
                    onClick={handleConfirmVerify}
                    className="px-4 py-2 rounded-xl bg-primary-container hover:bg-white text-on-primary-container text-xs font-bold transition-all disabled:opacity-40"
                  >
                    Confirm Link
                  </button>
                </div>
              </div>

              {verifyStatus && (
                <div
                  className={`p-3 rounded-xl border text-xs font-mono ${
                    verifyStatus.includes('failed')
                      ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                      : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                  }`}
                >
                  {verifyStatus}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
