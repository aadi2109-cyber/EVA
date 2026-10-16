import React, { useState } from 'react';

interface ChatInputProps {
  onSend: (text: string) => void;
  onTriggerScenario: (scenarioId: string) => void;
  isLoading: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  onSend,
  onTriggerScenario,
  isLoading,
}) => {
  const [text, setText] = useState<string>('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim() || isLoading) return;
    onSend(text.trim());
    setText('');
  };

  return (
    <div className="space-y-3">
      {/* Quick Scenario Pre-sets */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs">
        <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-outline shrink-0 mr-1">
          Scenarios:
        </span>
        <button
          type="button"
          onClick={() => onTriggerScenario('S1')}
          className="px-2.5 py-1 rounded-full bg-surface-container hover:bg-surface-container-high border border-white/5 text-on-surface-variant hover:text-white font-mono text-[11px] shrink-0 transition-colors"
        >
          S1: Ingest Emails & Sanitize Injection
        </button>
        <button
          type="button"
          onClick={() => onTriggerScenario('S2')}
          className="px-2.5 py-1 rounded-full bg-surface-container hover:bg-surface-container-high border border-rose-500/30 text-rose-300 font-mono text-[11px] shrink-0 transition-colors"
        >
          S2: Hijacked Send Denied
        </button>
        <button
          type="button"
          onClick={() => onTriggerScenario('S4')}
          className="px-2.5 py-1 rounded-full bg-surface-container hover:bg-surface-container-high border border-purple-500/30 text-purple-300 font-mono text-[11px] shrink-0 transition-colors"
        >
          S4: Exact Action Approval
        </button>
        <button
          type="button"
          onClick={() => onTriggerScenario('S7')}
          className="px-2.5 py-1 rounded-full bg-surface-container hover:bg-surface-container-high border border-orange-500/30 text-orange-300 font-mono text-[11px] shrink-0 transition-colors"
        >
          S7: Tier-2 Degraded Fail-Closed
        </button>
      </div>

      {/* Main Input Field */}
      <form
        onSubmit={handleSubmit}
        className="relative bg-surface-container-low border border-white/10 rounded-2xl p-2.5 shadow-xl focus-within:border-primary-container/50 transition-colors"
      >
        <textarea
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Ask EVA AI to inspect files, query emails, draft replies, or perform high-assurance tasks..."
          className="w-full bg-transparent text-sm text-white placeholder:text-on-surface-variant/60 focus:outline-none resize-none px-2"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
        />

        <div className="flex items-center justify-between pt-2 border-t border-white/5 px-1">
          <div className="flex items-center gap-2 text-xs text-outline">
            <span className="material-symbols-outlined text-[16px] text-primary-container">
              shield
            </span>
            <span className="hidden sm:inline text-[11px]">
              Guard: Pre-execution policy & post-scan enclave verification active
            </span>
          </div>

          <button
            type="submit"
            disabled={!text.trim() || isLoading}
            className="flex items-center gap-2 px-5 py-2 rounded-xl bg-primary-container text-on-primary-container font-bold text-xs shadow-[0_0_15px_rgba(200,243,34,0.3)] hover:scale-[1.02] active:scale-[0.98] transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <span className="material-symbols-outlined text-[16px] animate-spin">
                  sync
                </span>
                <span>Executing Task...</span>
              </>
            ) : (
              <>
                <span>Run with Guard</span>
                <span className="material-symbols-outlined text-[16px]">
                  arrow_forward
                </span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
