import React from 'react';
import { User } from '../api/types';

interface HeaderProps {
  currentTab: string;
  onSelectTab: (tab: string) => void;
  currentUser: User;
  onToggleRole: () => void;
  isTraceOpen: boolean;
  onToggleTrace: () => void;
  traceCount: number;
  isDegraded?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  currentTab,
  onSelectTab,
  currentUser,
  onToggleRole,
  isTraceOpen,
  onToggleTrace,
  traceCount,
  isDegraded = false,
}) => {
  const tabs = [
    { id: 'workspace', label: 'Workspace', icon: 'chat' },
    { id: 'settings-trace', label: 'Security & Settings', icon: 'shield_lock' },
    { id: 'connectors', label: 'Connectors', icon: 'hub' },
    { id: 'files', label: 'Files', icon: 'folder' },
    { id: 'history', label: 'History', icon: 'history' },
    ...(currentUser.role === 'admin'
      ? [{ id: 'admin', label: 'Admin Enclave', icon: 'security' }]
      : []),
  ];

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-surface/90 backdrop-blur-xl shadow-[0_4px_24px_rgba(0,0,0,0.6)] border-b border-white/5">
      <div className="h-16 w-full px-4 sm:px-6 flex items-center justify-between gap-4">
        {/* Brand & Breadcrumbs */}
        <div className="flex items-center gap-4">
          <div
            onClick={() => onSelectTab('workspace')}
            className="cursor-pointer flex items-center gap-2.5 bg-surface-container-lowest/90 px-3 py-1.5 rounded-xl border border-white/10 hover:border-primary-container/40 transition-colors"
          >
            <div className="w-6 h-6 rounded-lg bg-primary-container/20 border border-primary-container/50 flex items-center justify-center text-primary-container">
              <span className="material-symbols-outlined text-[16px]">verified_user</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="font-bold text-base text-white tracking-tight">EVA AI</span>
              <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant border border-white/10">
                v0.1.0-PROD
              </span>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="hidden md:flex items-center gap-1 bg-surface-container-lowest/60 p-1 rounded-xl border border-white/5">
            {tabs.map((tab) => {
              const isActive = currentTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => onSelectTab(tab.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    isActive
                      ? 'bg-surface-container-highest text-white shadow-[0_0_12px_rgba(200,243,34,0.15)] border border-primary-container/30'
                      : 'text-on-surface-variant hover:text-white hover:bg-surface-container-high'
                  }`}
                >
                  <span className="material-symbols-outlined text-[16px]">
                    {tab.icon}
                  </span>
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Right Status & Controls */}
        <div className="flex items-center gap-2.5 sm:gap-3">
          {/* Heartbeat Status */}
          <div
            className={`hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full border ${
              isDegraded
                ? 'bg-orange-500/10 border-orange-500/30 text-orange-400'
                : 'bg-surface-container px-3 py-1.5 border-white/5 text-on-surface-variant'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isDegraded
                  ? 'bg-orange-400 animate-ping'
                  : 'bg-primary-container animate-pulse shadow-[0_0_8px_#c8f322]'
              }`}
            />
            <span className="text-xs uppercase font-bold tracking-wider font-mono">
              {isDegraded ? 'Posture Degraded' : 'Enclave Active'}
            </span>
          </div>

          {/* Live Security Trace Toggle Button */}
          <button
            id="toggle-trace-btn"
            type="button"
            onClick={onToggleTrace}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full border text-xs font-semibold transition-all group ${
              isTraceOpen
                ? 'bg-primary-container/15 border-primary-container text-primary-container shadow-[0_0_16px_rgba(200,243,34,0.25)]'
                : 'bg-surface-container-high hover:bg-surface-container-highest border-primary-container/40 text-white shadow-[0_0_12px_rgba(200,243,34,0.12)]'
            }`}
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-container opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-primary-container"></span>
            </span>
            <span className="font-bold hidden sm:inline">Live Trace</span>
            <span className="font-mono text-[10px] px-1.5 py-0.2 rounded-full bg-surface-container-lowest text-primary-container border border-primary-container/30">
              {traceCount}
            </span>
            <span
              className={`material-symbols-outlined text-[16px] transition-transform ${
                isTraceOpen ? 'rotate-180' : ''
              }`}
            >
              expand_more
            </span>
          </button>

          {/* User Role Switcher & Avatar */}
          <div className="flex items-center gap-2 pl-1 border-l border-white/10">
            <button
              onClick={onToggleRole}
              title={`Click to switch role (Current: ${currentUser.role})`}
              className="text-[10px] font-mono font-bold px-2 py-1 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-primary-container border border-white/10 uppercase"
            >
              Role: {currentUser.role}
            </button>
            <div className="ring-2 ring-primary-container/30 rounded-full p-0.5">
              <div className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center font-bold text-xs text-white border border-white/10">
                {currentUser.name
                  .split(' ')
                  .map((n) => n[0])
                  .join('')}
              </div>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};
