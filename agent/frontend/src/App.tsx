import React, { useState } from 'react';
import { Header } from './components/Header';
import { DegradedBanner } from './components/DegradedBanner';
import { LiveTracePanel } from './components/LiveTracePanel';
import { ApprovalModal } from './components/ApprovalModal';
import { TaskWorkspace, ActiveToolCall } from './pages/TaskWorkspace';
import { SettingsTrace } from './pages/SettingsTrace';
import { Connectors } from './pages/Connectors';
import { FilesViewer } from './pages/FilesViewer';
import { History } from './pages/History';
import { Admin } from './pages/Admin';
import { Login } from './pages/Login';
import {
  User,
  ApprovalRequest,
  PlanStepPayload,
  TaskOutcomePayload,
  SecurityTraceItem,
  SSEMessage,
} from './api/types';
import { SCENARIOS, INITIAL_SECURITY_TRACE_ITEMS } from './mocks/mockStream';

export const App: React.FC = () => {
  // Authentication State
  const [currentUser, setCurrentUser] = useState<User | null>({
    id: 'usr_secops_01',
    name: 'Sophia Sterling',
    email: 'sophia.sterling@corp.internal',
    role: 'user',
  });

  // Navigation State
  const [currentTab, setCurrentTab] = useState<string>('workspace');

  // Live Security Trace State
  const [traceItems, setTraceItems] = useState<SecurityTraceItem[]>(
    INITIAL_SECURITY_TRACE_ITEMS
  );
  const [isTraceDrawerOpen, setIsTraceDrawerOpen] = useState<boolean>(false);

  // Health / Degraded State
  const [isDegraded, setIsDegraded] = useState<boolean>(false);
  const [degradedReason, setDegradedReason] = useState<string | undefined>(
    undefined
  );
  const [failureMode, setFailureMode] = useState<
    'fail_closed' | 'tier1_only_warning'
  >('fail_closed');

  // Active Task Execution State
  const [currentPrompt, setCurrentPrompt] = useState<string>('');
  const [assistantText, setAssistantText] = useState<string>('');
  const [steps, setSteps] = useState<PlanStepPayload[]>([]);
  const [toolCalls, setToolCalls] = useState<ActiveToolCall[]>([]);
  const [taskOutcome, setTaskOutcome] = useState<TaskOutcomePayload | undefined>(
    undefined
  );
  const [isExecuting, setIsExecuting] = useState<boolean>(false);

  // Approval Modal State
  const [activeApproval, setActiveApproval] = useState<ApprovalRequest | null>(
    null
  );

  // User role toggle (for quick testing admin views)
  const handleToggleRole = () => {
    if (!currentUser) return;
    const nextRole = currentUser.role === 'admin' ? 'user' : 'admin';
    setCurrentUser({
      ...currentUser,
      role: nextRole,
    });
  };

  // Replay Scenario Stream
  const runScenario = (scenarioId: string) => {
    const scenario = SCENARIOS[scenarioId];
    if (!scenario) return;

    setCurrentPrompt(scenario.title);
    setAssistantText('');
    setSteps([]);
    setToolCalls([]);
    setTaskOutcome(undefined);
    setIsExecuting(true);
    setActiveApproval(null);

    // If S7, activate degraded state
    if (scenarioId === 'S7') {
      setIsDegraded(true);
      setFailureMode('fail_closed');
      setDegradedReason(
        'Tier-2 Neural Enclave offline (latency SLO breach: 580ms). Strict posture enforcement active.'
      );
    } else {
      setIsDegraded(false);
    }

    // Playback events chronologically
    let delay = 300;
    scenario.events.forEach((msg: SSEMessage, index: number) => {
      setTimeout(() => {
        handleSSEEvent(msg);
        if (index === scenario.events.length - 1) {
          setIsExecuting(false);
        }
      }, delay);
      delay += 550;
    });
  };

  // Process incoming SSE messages (from mock replay or live server)
  const handleSSEEvent = (msg: SSEMessage) => {
    const { event, data } = msg;

    switch (event) {
      case 'model.delta':
        if (data.text) {
          setAssistantText((prev) => prev + data.text);
        }
        break;

      case 'plan.step':
        setSteps((prev) => {
          const existingIdx = prev.findIndex((s) => s.index === data.index);
          if (existingIdx >= 0) {
            const next = [...prev];
            next[existingIdx] = {
              index: data.index,
              title: data.title,
              status: data.status,
            };
            return next;
          }
          return [
            ...prev,
            { index: data.index, title: data.title, status: data.status },
          ];
        });
        break;

      case 'tool.requested':
        setToolCalls((prev) => [
          ...prev,
          {
            callId: data.call_id,
            tool: data.tool,
            args: data.args,
            argSources: data.arg_sources || {},
            isRunning: true,
          },
        ]);
        break;

      case 'guard.decision':
        setToolCalls((prev) =>
          prev.map((tc) =>
            tc.callId === data.call_id
              ? {
                  ...tc,
                  decision: {
                    call_id: data.call_id,
                    decision: data.decision,
                    reasons: data.reasons || [],
                    reason_text: data.reason_text || '',
                    align: data.align,
                  },
                  isRunning: data.decision === 'ALLOW',
                }
              : tc
          )
        );

        // Add to Live Trace
        const newTraceDecision: SecurityTraceItem = {
          id: `trc-gw-${Date.now().toString().slice(-4)}`,
          seq: traceItems.length + 1,
          timestamp: new Date().toLocaleTimeString() + ' UTC',
          type: 'decision',
          event: 'guard.decision',
          badge:
            data.decision === 'ALLOW'
              ? 'ALLOW'
              : data.decision === 'REQUIRE_APPROVAL'
              ? 'REQUIRE_APPROVAL'
              : 'DENY',
          origin: 'gateway-deterministic-01',
          title: `Tool call ${data.call_id} evaluated by policy gateway`,
          reasonCode: data.reasons?.[0] || 'DECISION_EVALUATED',
          plainEnglishReason:
            data.reason_text || 'Action validated against task policy rules.',
          call_id: data.call_id,
        };
        setTraceItems((prev) => [newTraceDecision, ...prev]);
        break;

      case 'tool.output':
        setToolCalls((prev) =>
          prev.map((tc) =>
            tc.callId === data.call_id
              ? {
                  ...tc,
                  output: data,
                  isRunning: false,
                }
              : tc
          )
        );
        break;

      case 'guard.scan':
        // Add to Live Trace
        const newTraceScan: SecurityTraceItem = {
          id: `trc-scan-${Date.now().toString().slice(-4)}`,
          seq: traceItems.length + 1,
          timestamp: new Date().toLocaleTimeString() + ' UTC',
          type: 'scan',
          event: 'guard.scan',
          badge:
            data.disposition === 'sanitized'
              ? 'SANITIZED'
              : data.disposition === 'quarantined'
              ? 'QUARANTINED'
              : data.disposition === 'held'
              ? 'HELD'
              : 'PASS',
          origin: 'inbound-sanitizer-enclave',
          title: `Tool output scan disposition: ${data.disposition}`,
          reasonCode: data.warnings?.[0] || 'SCAN_COMPLETE',
          plainEnglishReason: `Scanned with ${data.sentences_removed || 0} sentences removed by prompt firewall.`,
          call_id: data.call_id,
        };
        setTraceItems((prev) => [newTraceScan, ...prev]);
        break;

      case 'approval.required':
        setActiveApproval(data.approval);
        break;

      case 'approval.resolved':
        setActiveApproval(null);
        break;

      case 'health.degraded':
        setIsDegraded(true);
        setFailureMode(data.failure_mode || 'fail_closed');
        setDegradedReason(data.reason);

        const newTraceHealth: SecurityTraceItem = {
          id: `trc-deg-${Date.now().toString().slice(-4)}`,
          seq: traceItems.length + 1,
          timestamp: new Date().toLocaleTimeString() + ' UTC',
          type: 'health',
          event: 'health.degraded',
          badge: 'guard.error',
          origin: 'enclave-health-monitor',
          title: 'Enclave posture degraded event received',
          reasonCode: 'LATENCY_SLO_BREACH',
          plainEnglishReason:
            data.reason || 'Tier-2 latency breach triggered fail-closed mode.',
        };
        setTraceItems((prev) => [newTraceHealth, ...prev]);
        break;

      case 'state.verified':
        const newTraceState: SecurityTraceItem = {
          id: `trc-ver-${Date.now().toString().slice(-4)}`,
          seq: traceItems.length + 1,
          timestamp: new Date().toLocaleTimeString() + ' UTC',
          type: 'state',
          event: 'state.verified',
          badge: data.passed ? 'PASS' : 'DENY',
          origin: 'state-verifier-engine',
          title: data.passed
            ? 'State assertion verified: No unauthorized mutations'
            : 'State assertion failed: Mutation detected',
          reasonCode: data.passed
            ? 'STATE_ASSERTION_VALID'
            : 'MUTATION_ANOMALY',
          plainEnglishReason:
            'Observed state matched expected invariants strictly.',
        };
        setTraceItems((prev) => [newTraceState, ...prev]);
        break;

      case 'task.completed':
      case 'task.held':
      case 'task.failed':
        setTaskOutcome(data);
        setIsExecuting(false);
        break;
    }
  };

  const handleSendPrompt = (prompt: string) => {
    // If user types a prompt, start a simulated S1 task flow
    setCurrentPrompt(prompt);
    runScenario('S1');
  };

  const handleApproveAction = (
    approvalId: string,
    editedArgs?: Record<string, any>
  ) => {
    setActiveApproval(null);
    setAssistantText(
      (prev) =>
        prev +
        `\n\n[Action Approved]: Tool call authorized by user ${currentUser?.name}. Verified sent.`
    );
    setTaskOutcome({
      summary: {
        sentences_removed: 0,
        actions_denied: 0,
        approvals: 1,
      },
    });
  };

  const handleDenyAction = (approvalId: string) => {
    setActiveApproval(null);
    setAssistantText(
      (prev) => prev + `\n\n[Action Denied]: Tool execution aborted by user.`
    );
    setTaskOutcome({
      summary: {
        sentences_removed: 0,
        actions_denied: 1,
        approvals: 0,
      },
    });
  };

  if (!currentUser) {
    return <Login onLoginSuccess={(u) => setCurrentUser(u)} />;
  }

  return (
    <div className="min-h-screen bg-background text-on-surface font-sans selection:bg-primary-container selection:text-on-primary-container relative">
      {/* Persistent Navigation Header */}
      <Header
        currentTab={currentTab}
        onSelectTab={(tab) => setCurrentTab(tab)}
        currentUser={currentUser}
        onToggleRole={handleToggleRole}
        isTraceOpen={isTraceDrawerOpen}
        onToggleTrace={() => setIsTraceDrawerOpen(!isTraceDrawerOpen)}
        traceCount={traceItems.length}
        isDegraded={isDegraded}
      />

      {/* Main Container */}
      <main className="w-full pt-20 pb-24 min-h-screen px-4 sm:px-6 max-w-[1640px] mx-auto space-y-6">
        {/* Persistent Degraded Banner */}
        <DegradedBanner
          visible={isDegraded}
          failureMode={failureMode}
          reason={degradedReason}
        />

        {/* Global Live Trace Drawer / Overlay when toggled from Header */}
        {isTraceDrawerOpen && (
          <div className="animate-in fade-in slide-in-from-top-4 duration-200">
            <LiveTracePanel
              items={traceItems}
              onClose={() => setIsTraceDrawerOpen(false)}
            />
          </div>
        )}

        {/* Page Switcher */}
        {currentTab === 'workspace' && (
          <TaskWorkspace
            currentPrompt={currentPrompt}
            assistantText={assistantText}
            steps={steps}
            toolCalls={toolCalls}
            taskOutcome={taskOutcome}
            isExecuting={isExecuting}
            onSendPrompt={handleSendPrompt}
            onTriggerScenario={runScenario}
            onOpenTrace={() => setIsTraceDrawerOpen(true)}
            traceCount={traceItems.length}
          />
        )}

        {currentTab === 'settings-trace' && (
          <SettingsTrace
            traceItems={traceItems}
            currentUser={currentUser}
          />
        )}

        {currentTab === 'connectors' && <Connectors />}

        {currentTab === 'files' && <FilesViewer />}

        {currentTab === 'history' && (
          <History
            onReplayScenario={(scenId) => {
              setCurrentTab('workspace');
              runScenario(scenId);
            }}
          />
        )}

        {currentTab === 'admin' && <Admin />}
      </main>

      {/* Exact Action Approval Modal */}
      <ApprovalModal
        approval={activeApproval}
        onApprove={handleApproveAction}
        onDeny={handleDenyAction}
      />
    </div>
  );
};
