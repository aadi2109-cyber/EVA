import React from 'react';
import { PlanStepPayload } from '../api/types';

interface StepListProps {
  steps: PlanStepPayload[];
}

export const StepList: React.FC<StepListProps> = ({ steps }) => {
  if (steps.length === 0) return null;

  return (
    <div className="bg-surface-container-low/70 border border-white/5 rounded-xl p-3.5 my-3">
      <div className="flex items-center gap-2 mb-2.5">
        <span className="material-symbols-outlined text-[16px] text-primary-container">
          format_list_numbered
        </span>
        <span className="text-xs font-bold uppercase tracking-wider text-outline font-mono">
          Task Execution Plan ({steps.length} Steps)
        </span>
      </div>

      <div className="space-y-2">
        {steps.map((step) => {
          const isDone = step.status === 'completed';
          const isRunning = step.status === 'running';

          return (
            <div
              key={step.index}
              className={`p-2.5 rounded-lg border flex items-center justify-between text-xs transition-all ${
                isRunning
                  ? 'bg-surface-container-high border-primary-container/40 text-white shadow-sm'
                  : isDone
                  ? 'bg-surface-container/40 border-white/5 text-on-surface'
                  : 'bg-surface-container-lowest/40 border-white/5 text-on-surface-variant'
              }`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <span
                  className={`w-5 h-5 rounded-md flex items-center justify-center font-mono text-[10px] font-bold ${
                    isDone
                      ? 'bg-emerald-500/20 text-emerald-300'
                      : isRunning
                      ? 'bg-primary-container text-on-primary-container animate-pulse'
                      : 'bg-surface-container-high text-outline'
                  }`}
                >
                  {isDone ? '✓' : step.index + 1}
                </span>
                <span className="truncate font-medium">{step.title}</span>
              </div>

              <span
                className={`font-mono text-[10px] px-2 py-0.5 rounded-full font-bold uppercase shrink-0 ${
                  isDone
                    ? 'bg-emerald-500/10 text-emerald-300'
                    : isRunning
                    ? 'bg-primary-container/20 text-primary-container border border-primary-container/30'
                    : 'bg-surface-container text-outline'
                }`}
              >
                {step.status}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
