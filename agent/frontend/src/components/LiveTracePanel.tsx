import React, { useState } from 'react';
import { SecurityTraceItem } from '../api/types';

interface LiveTracePanelProps {
  items: SecurityTraceItem[];
  onClose?: () => void;
  isEmbedded?: boolean;
}

export const LiveTracePanel: React.FC<LiveTracePanelProps> = ({
  items,
  onClose,
  isEmbedded = false,
}) => {
  const [activeFilter, setActiveFilter] = useState<string>('all');
  const [selectedItem, setSelectedItem] = useState<SecurityTraceItem>(
    items[0] || null
  );
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const filteredItems = items.filter((item) => {
    if (activeFilter === 'all') return true;
    if (activeFilter === 'decision') return item.event === 'guard.decision';
    if (activeFilter === 'scan') return item.event === 'guard.scan';
    if (activeFilter === 'state') return item.event === 'state.verified';
    if (activeFilter === 'health')
      return item.event === 'health.degraded' || item.event === 'guard.error';
    return true;
  });

  const getBadgeStyle = (badge: SecurityTraceItem['badge']) => {
    switch (badge) {
      case 'DENY':
        return {
          bg: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
          dot: 'bg-rose-400',
          icon: 'gpp_bad',
          border: 'border-rose-500/40 hover:border-rose-400',
        };
      case 'QUARANTINED':
        return {
          bg: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
          dot: 'bg-amber-400',
          icon: 'lock_clock',
          border: 'border-amber-500/30 hover:border-amber-400',
        };
      case 'SANITIZED':
        return {
          bg: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40',
          dot: 'bg-cyan-400',
          icon: 'cleaning_services',
          border: 'border-cyan-500/30 hover:border-cyan-400',
        };
      case 'REQUIRE_APPROVAL':
        return {
          bg: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
          dot: 'bg-purple-400',
          icon: 'admin_panel_settings',
          border: 'border-purple-500/30 hover:border-purple-400',
        };
      case 'HELD':
        return {
          bg: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
          dot: 'bg-yellow-400',
          icon: 'pause_circle',
          border: 'border-yellow-500/30 hover:border-yellow-400',
        };
      case 'ALLOW':
      case 'PASS':
        return {
          bg: 'bg-primary-container/20 text-primary-container border-primary-container/40',
          dot: 'bg-primary-container',
          icon: 'verified',
          border: 'border-primary-container/30 hover:border-primary-container',
        };
      case 'guard.error':
      default:
        return {
          bg: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
          dot: 'bg-orange-400',
          icon: 'warning',
          border: 'border-orange-500/30 hover:border-orange-400',
        };
    }
  };

  const handleCopyId = (id: string) => {
    navigator.clipboard?.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleExportJson = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(items, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `eva-security-trace-${Date.now()}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const activeItem = selectedItem || items[0];

  return (
    <section
      id="live-trace-panel"
      className={`rounded-2xl bg-surface-container-low/95 border border-primary-container/30 backdrop-blur-2xl shadow-[0_20px_60px_rgba(0,0,0,0.8)] overflow-hidden transition-all duration-300 ${
        isEmbedded ? 'w-full' : 'w-full'
      }`}
    >
      {/* Top Bar with Filter Tabs */}
      <div className="px-4 sm:px-6 py-3.5 bg-surface-container-lowest/95 border-b border-white/10 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="font-mono font-bold text-xs uppercase tracking-wider text-primary-container flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-primary-container animate-ping"></span>
            STREAM // LIVE TELEMETRY
          </span>
          <span className="text-xs text-outline hidden md:inline">|</span>
          <span className="text-xs text-on-surface-variant font-mono hidden md:inline">
            Node: apex-shield-enclave-01
          </span>
        </div>

        {/* Filter Buttons */}
        <div className="flex flex-wrap items-center gap-1.5 text-xs font-semibold">
          <button
            onClick={() => setActiveFilter('all')}
            className={`px-3 py-1 rounded-lg transition-colors ${
              activeFilter === 'all'
                ? 'bg-primary-container text-on-primary-container font-bold'
                : 'bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-white'
            }`}
          >
            All ({items.length})
          </button>
          <button
            onClick={() => setActiveFilter('decision')}
            className={`px-3 py-1 rounded-lg transition-colors ${
              activeFilter === 'decision'
                ? 'bg-primary-container text-on-primary-container font-bold'
                : 'bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-white'
            }`}
          >
            guard.decision
          </button>
          <button
            onClick={() => setActiveFilter('scan')}
            className={`px-3 py-1 rounded-lg transition-colors ${
              activeFilter === 'scan'
                ? 'bg-primary-container text-on-primary-container font-bold'
                : 'bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-white'
            }`}
          >
            guard.scan
          </button>
          <button
            onClick={() => setActiveFilter('state')}
            className={`px-3 py-1 rounded-lg transition-colors ${
              activeFilter === 'state'
                ? 'bg-primary-container text-on-primary-container font-bold'
                : 'bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-white'
            }`}
          >
            state.verified
          </button>
          <button
            onClick={() => setActiveFilter('health')}
            className={`px-3 py-1 rounded-lg transition-colors ${
              activeFilter === 'health'
                ? 'bg-primary-container text-on-primary-container font-bold'
                : 'bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-white'
            }`}
          >
            health / error
          </button>

          {onClose && (
            <button
              onClick={onClose}
              className="p-1 rounded-lg bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-white border border-white/5 ml-2"
              title="Close Panel"
            >
              <span className="material-symbols-outlined text-[18px]">
                keyboard_arrow_up
              </span>
            </button>
          )}
        </div>
      </div>

      {/* Main Content: Left Event Stream (7 cols) + Right Inspector Card (5 cols) */}
      <div className="grid grid-cols-1 xl:grid-cols-12 divide-y xl:divide-y-0 xl:divide-x divide-white/10">
        {/* Left List of Chronological Events */}
        <div
          className="xl:col-span-7 p-4 space-y-2.5 max-h-[580px] overflow-y-auto"
          id="trace-list-container"
        >
          {filteredItems.length === 0 ? (
            <div className="text-center py-12 text-on-surface-variant text-xs">
              No telemetry events recorded under this filter.
            </div>
          ) : (
            filteredItems.map((item) => {
              const style = getBadgeStyle(item.badge);
              const isSelected = activeItem?.id === item.id;

              return (
                <div
                  key={item.id}
                  onClick={() => setSelectedItem(item)}
                  className={`cursor-pointer p-3.5 rounded-xl transition-all group border ${
                    isSelected
                      ? `${style.border} bg-surface-container-lowest ring-1 ring-white/10 shadow-lg`
                      : 'border-white/5 bg-surface-container-lowest/60 hover:border-white/20 hover:bg-surface-container-lowest/90'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <span
                        className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 border font-mono text-xs ${style.bg}`}
                      >
                        <span className="material-symbols-outlined text-[16px]">
                          {style.icon}
                        </span>
                      </span>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className={`font-mono font-bold text-xs ${
                              item.badge === 'DENY'
                                ? 'text-rose-400'
                                : item.badge === 'QUARANTINED'
                                ? 'text-amber-300'
                                : item.badge === 'SANITIZED'
                                ? 'text-cyan-300'
                                : item.badge === 'REQUIRE_APPROVAL'
                                ? 'text-purple-300'
                                : item.badge === 'HELD'
                                ? 'text-yellow-300'
                                : item.badge === 'guard.error'
                                ? 'text-orange-300'
                                : 'text-primary-container'
                            }`}
                          >
                            {item.event}
                          </span>
                          <span className="font-mono text-[11px] text-outline">
                            {item.id}
                          </span>
                          <span className="font-mono text-[10px] text-on-surface-variant bg-surface-container-high px-1.5 py-0.5 rounded">
                            {item.timestamp}
                          </span>
                        </div>
                        <p className="text-xs text-on-surface-variant truncate mt-0.5">
                          {item.title}
                        </p>
                      </div>
                    </div>

                    {/* Accessible Status Badge */}
                    <span
                      className={`px-2.5 py-1 rounded-full font-mono text-[11px] font-bold border flex items-center gap-1 shrink-0 ${style.bg}`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${style.dot}`}
                      ></span>
                      {item.badge}
                    </span>
                  </div>

                  <div className="mt-2 pt-2 border-t border-white/5 flex items-center justify-between font-mono text-[11px] text-outline">
                    <span>
                      Origin: <span className="text-white">{item.origin}</span>
                    </span>
                    <span className="font-semibold truncate ml-2 text-on-surface-variant">
                      {item.reasonCode}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Right: Detailed Trace Inspection Card */}
        <div
          className="xl:col-span-5 p-5 bg-surface-container-lowest/90 flex flex-col justify-between space-y-4"
          id="trace-detail-card"
        >
          {activeItem ? (
            <div className="space-y-4">
              {/* Status & Title */}
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2.5 py-1 rounded-full font-mono text-xs font-bold border flex items-center gap-1 ${
                      getBadgeStyle(activeItem.badge).bg
                    }`}
                  >
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${
                        getBadgeStyle(activeItem.badge).dot
                      }`}
                    ></span>
                    {activeItem.badge}
                  </span>
                  <span className="font-mono font-bold text-sm text-white">
                    {activeItem.event}
                  </span>
                </div>
                <span className="font-mono text-xs text-outline">
                  {activeItem.timestamp}
                </span>
              </div>

              {/* Metadata Grid */}
              <div className="p-3 rounded-xl bg-surface-container-high/60 border border-white/5 space-y-2 font-mono text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-outline">Trace Event ID:</span>
                  <span className="text-white font-bold">{activeItem.id}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-outline">Origin Enclave:</span>
                  <span className="text-primary-container font-medium">
                    {activeItem.origin}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-outline">Reason Code:</span>
                  <span className="text-rose-400 font-semibold">
                    {activeItem.reasonCode}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-outline">Attestation Level:</span>
                  <span className="text-on-surface">
                    Strict // Enclave Validated
                  </span>
                </div>
              </div>

              {/* Plain-English Audit Verdict */}
              <div className="space-y-1.5">
                <span className="text-xs font-bold uppercase tracking-wider text-outline block">
                  Plain-English Audit Reason
                </span>
                <p className="text-xs text-on-surface leading-relaxed p-3.5 rounded-xl bg-surface-container/70 border border-white/5 font-sans">
                  {activeItem.plainEnglishReason}
                </p>
              </div>

              {/* Privacy & Zero Raw Text Guarantee Box */}
              <div className="p-3 rounded-xl bg-surface-container-high/40 border border-primary-container/20 flex items-start gap-2.5">
                <span className="material-symbols-outlined text-primary-container text-[20px] shrink-0 mt-0.5">
                  lock_person
                </span>
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-bold text-white">
                      Privacy Guarantee: Zero Raw Text
                    </span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-primary-container/20 text-primary-container border border-primary-container/30 font-bold">
                      Redacted at Enclave Boundary
                    </span>
                  </div>
                  <p className="text-[11px] text-on-surface-variant leading-snug">
                    EVA Enclave policy never stores or transmits raw unvetted
                    payload text. Only SHA-256 cryptographic hashes and heuristic
                    vector embeddings are audited to prevent exfiltration.
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-12 text-outline text-xs">
              Select an event to view full enclave telemetry inspection.
            </div>
          )}

          {/* Action Controls */}
          <div className="pt-3 border-t border-white/10 flex flex-wrap items-center gap-2">
            <button
              onClick={handleExportJson}
              type="button"
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-primary-container text-on-primary-container text-xs font-bold shadow-[0_0_15px_rgba(200,243,34,0.3)] hover:scale-[1.02] active:scale-[0.98] transition-all"
            >
              <span className="material-symbols-outlined text-[16px]">
                download
              </span>
              <span>Export Audit JSON</span>
            </button>
            <button
              onClick={() => activeItem && handleCopyId(activeItem.id)}
              type="button"
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-surface-container-high hover:bg-surface-container-highest text-white text-xs font-semibold border border-white/5 transition-colors"
            >
              <span className="material-symbols-outlined text-[16px]">
                {copiedId === activeItem?.id ? 'check' : 'content_copy'}
              </span>
              <span>
                {copiedId === activeItem?.id ? 'Copied!' : 'Copy Trace ID'}
              </span>
            </button>
            <button
              type="button"
              className="px-3 py-2 rounded-xl bg-surface-container-high hover:bg-surface-container-highest text-primary-container text-xs font-bold border border-white/5 transition-colors"
              title="Acknowledge Audit"
            >
              <span className="material-symbols-outlined text-[16px]">
                done_all
              </span>
            </button>
          </div>
        </div>
      </div>
    </section>
  );
};
