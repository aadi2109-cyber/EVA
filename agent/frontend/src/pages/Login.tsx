import React, { useState } from 'react';
import { User } from '../api/types';

interface LoginProps {
  onLoginSuccess: (user: User, token: string) => void;
}

export const Login: React.FC<LoginProps> = ({ onLoginSuccess }) => {
  const [email, setEmail] = useState<string>('sophia.sterling@corp.internal');
  const [password, setPassword] = useState<string>('••••••••••••');
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    setTimeout(() => {
      setIsLoading(false);
      onLoginSuccess(
        {
          id: 'usr_secops_01',
          name: 'Sophia Sterling',
          email: email || 'sophia.sterling@corp.internal',
          role: email.includes('admin') ? 'admin' : 'user',
        },
        'mock-jwt-token-eva-auth'
      );
    }, 600);
  };

  const handleQuickDemo = (role: 'user' | 'admin') => {
    if (role === 'admin') {
      setEmail('admin.root@corp.internal');
      onLoginSuccess(
        {
          id: 'usr_admin_root',
          name: 'Admin Overseer',
          email: 'admin.root@corp.internal',
          role: 'admin',
        },
        'mock-jwt-token-admin'
      );
    } else {
      setEmail('sophia.sterling@corp.internal');
      onLoginSuccess(
        {
          id: 'usr_secops_01',
          name: 'Sophia Sterling',
          email: 'sophia.sterling@corp.internal',
          role: 'user',
        },
        'mock-jwt-token-user'
      );
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-background relative overflow-hidden">
      {/* Background Glow */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-96 h-96 bg-primary-container/10 rounded-full blur-[140px] pointer-events-none" />

      <div className="w-full max-w-md bg-surface-container-low/90 backdrop-blur-2xl border border-white/10 rounded-3xl p-8 shadow-[0_25px_80px_rgba(0,0,0,0.8)] relative z-10 space-y-6">
        {/* Brand */}
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-2xl bg-primary-container/15 border border-primary-container/40 text-primary-container flex items-center justify-center mx-auto shadow-[0_0_20px_rgba(200,243,34,0.3)]">
            <span className="material-symbols-outlined text-[28px]">
              verified_user
            </span>
          </div>
          <h2 className="text-xl font-bold text-white tracking-tight">
            EVA AI Enclave Access
          </h2>
          <p className="text-xs text-on-surface-variant">
            Zero-Trust Agent Workstation with Deterministic Policy Enclave
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div className="space-y-1">
            <label className="font-bold text-white uppercase tracking-wider text-[11px] block">
              Enclave Identity (Email)
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl bg-surface-container-lowest border border-white/10 text-white font-mono focus:outline-none focus:ring-1 focus:ring-primary-container"
            />
          </div>

          <div className="space-y-1">
            <label className="font-bold text-white uppercase tracking-wider text-[11px] block">
              Security Token (Password)
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl bg-surface-container-lowest border border-white/10 text-white font-mono focus:outline-none focus:ring-1 focus:ring-primary-container"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 rounded-xl bg-primary-container text-on-primary-container font-bold text-xs shadow-[0_0_20px_rgba(200,243,34,0.35)] hover:scale-[1.01] active:scale-[0.99] transition-all flex items-center justify-center gap-2"
          >
            {isLoading ? (
              <span className="material-symbols-outlined text-[16px] animate-spin">
                sync
              </span>
            ) : (
              <span className="material-symbols-outlined text-[16px]">
                login
              </span>
            )}
            <span>Authenticate Session</span>
          </button>
        </form>

        {/* Demo Quick Select */}
        <div className="pt-4 border-t border-white/5 space-y-2">
          <span className="text-[10px] font-mono text-outline block text-center uppercase tracking-wider">
            Quick Demonstration Credentials
          </span>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => handleQuickDemo('user')}
              className="py-2 px-3 rounded-xl bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-white border border-white/5 text-[11px] font-medium transition-colors"
            >
              Demo User (Sophia)
            </button>
            <button
              type="button"
              onClick={() => handleQuickDemo('admin')}
              className="py-2 px-3 rounded-xl bg-surface-container hover:bg-surface-container-high text-primary-container border border-primary-container/20 text-[11px] font-medium transition-colors"
            >
              Demo Admin (Enclave)
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
