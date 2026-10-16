import React, { useState } from 'react';
import { GuardDecisionPayload, ToolOutputPayload } from '../api/types';

interface ToolCallCardProps {
  callId: string;
  tool: string;
  args: Record<string, any>;
  argSources?: Record<string, string>;
  decision?: GuardDecisionPayload;
  output?: ToolOutputPayload;
  isRunning?: boolean;
}

export const ToolCallCard: React.FC<ToolCallCardProps> = ({
  callId,
  tool,
  args,
  argSources = {},
  decision,
  output,
  isRunning = false,
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(true);

  const getDecisionBadge = () => {
    if (isRunning) {
      return (
        <span className="px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 font-mono text-[10px] font-bold border border-cyan-500/40 flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-spin"></span>
          EXECUTING
        </span>
      );
    }
    if (!decision) {
      return (
        <span className="px-2 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant font-mono text-[10px] font-bold border border-white/10">
          GATEWAY PENDING
        </span>
      );
    }

    switch (decision.decision) {
      case 'ALLOW':
        return (
          <span className="px-2 py-0.5 rounded-full bg-primary-container/20 text-primary-container font-mono text-[10px] font-bold border border-primary-container/40 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-primary-container"></span>
            ALLOW
          </span>
        );
      case 'REQUIRE_APPROVAL':
        return (
          <span className="px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 font-mono text-[10px] font-bold border border-purple-500/40 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
            REQUIRE_APPROVAL
          </span>
        );
      case 'DENY':
      default:
        return (
          <span className="px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 font-mono text-[10px] font-bold border border-rose-500/40 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
            DENY
          </span>
        );
    }
  };

  const sentencesRemoved = output?.scan?.fields?.reduce(
    (acc, f) => acc + (f.sentences_removed || 0),
    0
  ) || (output?.scan?.disposition === 'sanitized' ? 1 : 0);

  return (
    <div className="rounded-xl bg-surface-container-low border border-white/10 overflow-hidden shadow-md my-2.5">
      {/* Tool Call Header */}
      <div
        onClick={() => setIsExpanded(!isExpanded)}
        className="px-4 py-2.5 bg-surface-container/70 border-b border-white/5 flex items-center justify-between cursor-pointer hover:bg-surface-container transition-colors"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-6 h-6 rounded-lg bg-surface-container-high border border-white/10 flex items-center justify-center text-primary-container">
            <span className="material-symbols-outlined text-[15px]">
              build_circle
            </span>
          </div>
          <div className="flex items-center gap-2 flex-wrap min-w-0">
            <span className="font-mono font-bold text-xs text-white">
              {tool}
            </span>
            <span className="font-mono text-[10px] text-outline">
              ({callId})
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {sentencesRemoved > 0 && (
            <span className="px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 font-mono text-[10px] font-bold border border-cyan-500/30 flex items-center gap-1">
              <span className="material-symbols-outlined text-[12px]">
                cleaning_services
              </span>
              {sentencesRemoved} removed
            </span>
          )}
          {getDecisionBadge()}
          <span
            className={`material-symbols-outlined text-[16px] text-on-surface-variant transition-transform ${
              isExpanded ? 'rotate-180' : ''
            }`}
          >
            expand_more
          </span>
        </div>
      </div>

      {/* Collapsible Content */}
      {isExpanded && (
        <div className="p-4 space-y-3 bg-surface-container-lowest/60 text-xs">
          {/* Arguments Grid */}
          <div className="space-y-1.5">
            <span className="text-[11px] font-bold uppercase tracking-wider text-outline block">
              Arguments & Sources
            </span>
            <div className="space-y-1.5">
              {Object.entries(args || {}).map(([argKey, argVal]) => {
                const source = argSources[argKey] || 'system';
                const isUser =
                  source.toLowerCase().includes('user') ||
                  source.toLowerCase().includes('you');

                return (
                  <div
                    key={argKey}
                    className="p-2 rounded-lg bg-surface-container-low border border-white/5 flex flex-col sm:flex-row sm:items-center justify-between gap-1 font-mono"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-primary-container font-semibold">
                        {argKey}:
                      </span>
                      <span className="text-white truncate max-w-sm">
                        {typeof argVal === 'object'
                          ? JSON.stringify(argVal)
                          : String(argVal)}
                      </span>
                    </div>
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded border self-start sm:self-auto ${
                        isUser
                          ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                          : 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                      }`}
                    >
                      {source}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Decision Reason */}
          {decision?.reason_text && (
            <div className="p-2.5 rounded-lg bg-surface-container border border-white/5 space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-outline block font-mono">
                Gateway Evaluation
              </span>
              <p className="text-[11px] text-on-surface">
                {decision.reason_text}
              </p>
            </div>
          )}

          {/* Sanitized Tool Output */}
          {output && (
            <div className="space-y-1.5 pt-1 border-t border-white/5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-wider text-outline block">
                  Sanitized Tool Result
                </span>
                <span className="font-mono text-[10px] text-cyan-400">
                  Disposition: {output.scan?.disposition || 'pass'}
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-surface-container-high/40 border border-white/5 font-mono text-[11px] text-on-surface overflow-x-auto max-h-48 whitespace-pre-wrap">
                {(() => {
                  const r = output.sanitized_output ?? output.result;
                  if (r === undefined || r === null) return '(no output)';
                  return typeof r === 'object' ? JSON.stringify(r, null, 2) : String(r);
                })()}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
