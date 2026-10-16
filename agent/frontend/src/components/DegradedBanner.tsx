import React from 'react';

interface DegradedBannerProps {
  visible: boolean;
  failureMode?: 'fail_closed' | 'tier1_only_warning';
  reason?: string;
}

export const DegradedBanner: React.FC<DegradedBannerProps> = ({
  visible,
  failureMode = 'fail_closed',
  reason = 'Tier-2 Neural Enclave offline. High-assurance side-effect execution is suspended.',
}) => {
  if (!visible) return null;

  return (
    <div className="bg-gradient-to-r from-orange-950/80 via-amber-950/80 to-orange-950/80 border-b border-orange-500/40 text-orange-200 px-4 py-2.5 shadow-lg backdrop-blur-md relative z-40">
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-lg bg-orange-500/20 border border-orange-500/50 flex items-center justify-center text-orange-400 shrink-0">
            <span className="material-symbols-outlined text-[16px]">warning</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-white tracking-wide uppercase font-mono">
                SECURITY POSTURE DEGRADED — {failureMode.toUpperCase()}
              </span>
              <span className="bg-orange-500/30 text-orange-300 font-mono text-[10px] px-1.5 py-0.5 rounded border border-orange-500/40 font-bold">
                POSTURE_DEGRADED
              </span>
            </div>
            <p className="text-orange-200/90 text-[11px] mt-0.5">
              {reason} <span className="font-bold text-white">All external side-effect tools (gmail.send, files.write, messages.send) are strictly disabled.</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto font-mono text-[11px]">
          <span className="px-2 py-1 rounded bg-black/40 border border-orange-500/30 text-orange-300">
            Enclave Mode: Read-Only
          </span>
        </div>
      </div>
    </div>
  );
};
