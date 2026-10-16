import React, { useState, useEffect } from 'react';
import { ApprovalRequest } from '../api/types';

interface ApprovalModalProps {
  approval: ApprovalRequest | null;
  onApprove: (approvalId: string, editedArgs?: Record<string, any>) => void;
  onDeny: (approvalId: string) => void;
}

export const ApprovalModal: React.FC<ApprovalModalProps> = ({
  approval,
  onApprove,
  onDeny,
}) => {
  if (!approval) return null;

  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editedArgs, setEditedArgs] = useState<Record<string, any>>({});
  const [hasEdited, setHasEdited] = useState<boolean>(false);
  const [timeLeft, setTimeLeft] = useState<number>(300);

  useEffect(() => {
    setEditedArgs(approval.exact_action.args || {});
    setHasEdited(false);
    setIsEditing(false);

    // Calculate expiry seconds
    const exp = new Date(approval.expires_at).getTime();
    const remaining = Math.max(0, Math.floor((exp - Date.now()) / 1000));
    setTimeLeft(remaining > 0 ? remaining : 300);

    const interval = setInterval(() => {
      setTimeLeft((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);

    return () => clearInterval(interval);
  }, [approval]);

  const handleArgChange = (key: string, value: string) => {
    setEditedArgs((prev) => ({
      ...prev,
      [key]: value,
    }));
    setHasEdited(true);
  };

  const minutes = Math.floor(timeLeft / 60);
  const seconds = timeLeft % 60;
  const formattedTime = `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
      <div className="w-full max-w-2xl bg-surface-container-low border border-primary-container/40 rounded-2xl shadow-[0_25px_80px_rgba(0,0,0,0.9)] overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="px-6 py-4 bg-surface-container-lowest border-b border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-purple-500/20 text-purple-300 border border-purple-500/40 flex items-center justify-center">
              <span className="material-symbols-outlined text-[20px]">
                admin_panel_settings
              </span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-white text-base">
                  High-Assurance Action Authorization
                </h3>
                <span className="font-mono text-[10px] px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/40 font-bold">
                  REQUIRE_APPROVAL
                </span>
              </div>
              <p className="text-xs text-on-surface-variant font-mono">
                Approval ID: {approval.approval_id}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 font-mono text-xs bg-surface-container px-3 py-1.5 rounded-lg border border-white/10">
            <span className="material-symbols-outlined text-[16px] text-amber-400">
              timer
            </span>
            <span
              className={timeLeft < 60 ? 'text-rose-400 font-bold' : 'text-white'}
            >
              Expires in {formattedTime}
            </span>
          </div>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
          {/* Target Tool Action */}
          <div className="space-y-1.5">
            <span className="text-xs font-bold uppercase tracking-wider text-outline block">
              Exact Action to Execute
            </span>
            <div className="p-3 bg-surface-container-lowest rounded-xl border border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-2 font-mono text-sm">
                <span className="text-primary-container font-bold">Tool:</span>
                <span className="text-white px-2 py-0.5 rounded bg-surface-container-high border border-white/10">
                  {approval.exact_action.tool}
                </span>
              </div>
              <span className="font-mono text-[11px] text-outline">
                Hash: {approval.action_hash.slice(0, 16)}...
              </span>
            </div>
          </div>

          {/* Action Arguments with Provenance Sources */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-outline">
                Arguments & Provenance Sources
              </span>
              <button
                type="button"
                onClick={() => setIsEditing(!isEditing)}
                className="text-xs text-primary-container hover:underline font-semibold flex items-center gap-1"
              >
                <span className="material-symbols-outlined text-[14px]">
                  {isEditing ? 'lock' : 'edit'}
                </span>
                {isEditing ? 'Lock Arguments' : 'Edit Arguments'}
              </button>
            </div>

            <div className="space-y-2">
              {Object.entries(approval.exact_action.args || {}).map(([argName, argVal]) => {
                const source =
                  approval.arg_sources?.[argName] || 'unspecified source';
                const isUserSupplied =
                  source.toLowerCase().includes('user') ||
                  source.toLowerCase().includes('you');

                return (
                  <div
                    key={argName}
                    className="p-3 rounded-xl bg-surface-container border border-white/5 space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-xs text-primary-container">
                        {argName}
                      </span>
                      <span
                        className={`font-mono text-[10px] px-2 py-0.5 rounded-full border ${
                          isUserSupplied
                            ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                            : 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                        }`}
                      >
                        Source: {source}
                      </span>
                    </div>

                    {isEditing ? (
                      <textarea
                        rows={argName === 'body' || typeof argVal === 'object' ? 3 : 1}
                        value={
                          typeof editedArgs[argName] === 'object'
                            ? JSON.stringify(editedArgs[argName], null, 2)
                            : editedArgs[argName] ?? ''
                        }
                        onChange={(e) => handleArgChange(argName, e.target.value)}
                        className="w-full bg-surface-container-lowest border border-primary-container/40 rounded-lg p-2 text-xs font-mono text-white focus:outline-none focus:ring-1 focus:ring-primary-container"
                      />
                    ) : (
                      <div className="font-mono text-xs text-white p-2 bg-surface-container-lowest rounded-lg border border-white/5 overflow-x-auto whitespace-pre-wrap">
                        {typeof argVal === 'object'
                          ? JSON.stringify(argVal, null, 2)
                          : String(argVal)}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Voiding Notice if Edited */}
          {hasEdited && (
            <div className="p-3 rounded-xl bg-amber-500/15 border border-amber-500/30 flex items-start gap-2.5">
              <span className="material-symbols-outlined text-amber-400 text-[18px] shrink-0 mt-0.5">
                info
              </span>
              <p className="text-xs text-amber-200">
                <span className="font-bold">Notice:</span> Editing action
                arguments will void cryptographic hash{' '}
                <span className="font-mono text-white">
                  {approval.action_hash.slice(0, 12)}...
                </span>
                . The action will be re-submitted through the policy gateway for
                re-approval.
              </p>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 bg-surface-container-lowest border-t border-white/10 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => onDeny(approval.approval_id)}
            className="px-5 py-2.5 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 font-bold text-xs border border-rose-500/40 transition-colors flex items-center gap-1.5"
          >
            <span className="material-symbols-outlined text-[16px]">close</span>
            <span>Deny & Abort Action</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() =>
                onApprove(
                  approval.approval_id,
                  hasEdited ? editedArgs : undefined
                )
              }
              className="px-6 py-2.5 rounded-xl bg-primary-container hover:bg-white text-on-primary-container font-bold text-xs shadow-[0_0_20px_rgba(200,243,34,0.35)] transition-all flex items-center gap-1.5 hover:scale-[1.02] active:scale-[0.98]"
            >
              <span className="material-symbols-outlined text-[18px]">
                check_circle
              </span>
              <span>
                {hasEdited ? 'Submit for Re-Approval' : 'Approve & Execute'}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
