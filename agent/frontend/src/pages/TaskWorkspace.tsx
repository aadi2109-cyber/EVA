import React from 'react';
import { StepList } from '../components/StepList';
import { ToolCallCard } from '../components/ToolCallCard';
import { TaskSummaryLine } from '../components/TaskSummaryLine';
import { ChatInput } from '../components/ChatInput';
import {
  PlanStepPayload,
  GuardDecisionPayload,
  ToolOutputPayload,
  TaskOutcomePayload,
} from '../api/types';

export interface ActiveToolCall {
  callId: string;
  tool: string;
  args: Record<string, any>;
  argSources: Record<string, string>;
  decision?: GuardDecisionPayload;
  output?: ToolOutputPayload;
  isRunning?: boolean;
}

interface TaskWorkspaceProps {
  currentPrompt: string;
  assistantText: string;
  steps: PlanStepPayload[];
  toolCalls: ActiveToolCall[];
  taskOutcome?: TaskOutcomePayload;
  isExecuting: boolean;
  onSendPrompt: (prompt: string) => void;
  onTriggerScenario: (scenarioId: string) => void;
  onOpenTrace: () => void;
  traceCount: number;
}

export const TaskWorkspace: React.FC<TaskWorkspaceProps> = ({
  currentPrompt,
  assistantText,
  steps,
  toolCalls,
  taskOutcome,
  isExecuting,
  onSendPrompt,
  onTriggerScenario,
  onOpenTrace,
  traceCount,
}) => {
  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Top Banner / Hero */}
      <section className="bg-surface-container-low/90 backdrop-blur-xl p-5 rounded-2xl border border-white/10 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary-container/15 border border-primary-container/40 text-primary-container flex items-center justify-center shadow-[0_0_16px_rgba(200,243,34,0.25)]">
            <span className="material-symbols-outlined text-[24px]">terminal</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-white tracking-tight">
                High-Assurance Task Workspace
              </h1>
              <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                ACTIVE GUARD
              </span>
            </div>
            <p className="text-xs text-on-surface-variant">
              Every tool call is pre-validated by the deterministic gateway; all tool outputs pass zero-shot sanitization.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={onOpenTrace}
            className="flex items-center gap-2 px-4 py-2 rounded-full bg-surface-container-high hover:bg-surface-container-highest border border-primary-container/40 text-white text-xs font-semibold shadow-sm transition-all"
          >
            <span className="w-2 h-2 rounded-full bg-primary-container animate-ping" />
            <span>Telemetry Trace</span>
            <span className="font-mono text-[10px] px-1.5 py-0.5 rounded-full bg-surface-container-lowest text-primary-container">
              {traceCount}
            </span>
          </button>
        </div>
      </section>

      {/* Task Execution Feed */}
      <section className="bg-surface-container-lowest/80 border border-white/5 rounded-2xl p-5 sm:p-6 shadow-2xl min-h-[420px] flex flex-col justify-between">
        <div className="space-y-4">
          {/* User Request Bubble */}
          {currentPrompt ? (
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-full bg-surface-container-high border border-white/10 flex items-center justify-center font-bold text-xs text-white shrink-0">
                U
              </div>
              <div className="bg-surface-container p-4 rounded-2xl rounded-tl-sm border border-white/5 max-w-2xl">
                <span className="text-[10px] font-mono uppercase tracking-wider text-outline block mb-1">
                  Authenticated User Goal
                </span>
                <p className="text-sm text-white font-medium whitespace-pre-wrap">
                  {currentPrompt}
                </p>
              </div>
            </div>
          ) : (
            <div className="text-center py-16 text-on-surface-variant space-y-2">
              <div className="w-12 h-12 rounded-2xl bg-surface-container mx-auto flex items-center justify-center text-primary-container border border-white/5">
                <span className="material-symbols-outlined text-[24px]">chat</span>
              </div>
              <h3 className="text-sm font-semibold text-white">No active task session</h3>
              <p className="text-xs max-w-md mx-auto">
                Type an instruction below or select a quick demonstration scenario to witness EVA's deterministic policy enforcement and zero-shot prompt firewall.
              </p>
            </div>
          )}

          {/* Plan Step Progress */}
          <StepList steps={steps} />

          {/* Tool Calls Stream */}
          {toolCalls.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-outline">
                  Tool Operations & Enclave Inspections ({toolCalls.length})
                </span>
              </div>
              {toolCalls.map((tc) => (
                <ToolCallCard
                  key={tc.callId}
                  callId={tc.callId}
                  tool={tc.tool}
                  args={tc.args}
                  argSources={tc.argSources}
                  decision={tc.decision}
                  output={tc.output}
                  isRunning={tc.isRunning}
                />
              ))}
            </div>
          )}

          {/* Assistant Final Output */}
          {assistantText && (
            <div className="flex items-start gap-3 mt-4">
              <div className="w-8 h-8 rounded-full bg-primary-container/20 border border-primary-container/40 flex items-center justify-center text-primary-container shrink-0">
                <span className="material-symbols-outlined text-[16px]">smart_toy</span>
              </div>
              <div className="bg-surface-container-low p-4 rounded-2xl rounded-tl-sm border border-white/10 max-w-3xl flex-1 shadow-lg">
                <div className="flex items-center justify-between border-b border-white/5 pb-2 mb-2">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-primary-container font-bold flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-primary-container" />
                    EVA AI Verified Output
                  </span>
                  <span className="text-[10px] font-mono text-outline">
                    Plain-Text Sanitized Renderer Active
                  </span>
                </div>
                {/* Note: Untrusted images disabled, rendered safely as plain text / markdown */}
                <div className="text-sm text-on-surface whitespace-pre-wrap leading-relaxed font-sans">
                  {assistantText}
                </div>
              </div>
            </div>
          )}

          {/* Task Outcome Summary Line */}
          <TaskSummaryLine
            summary={taskOutcome?.summary}
            isCompleted={Boolean(taskOutcome)}
          />
        </div>

        {/* Input Bar */}
        <div className="mt-6 pt-4 border-t border-white/5">
          <ChatInput
            onSend={onSendPrompt}
            onTriggerScenario={onTriggerScenario}
            isLoading={isExecuting}
          />
        </div>
      </section>
    </div>
  );
};
