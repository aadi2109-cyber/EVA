import { describe, it, expect, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StepList } from '../src/components/StepList';
import { ToolCallCard } from '../src/components/ToolCallCard';
import { ApprovalModal } from '../src/components/ApprovalModal';
import { ApprovalRequest } from '../src/api/types';

const approval: ApprovalRequest = {
  approval_id: 'appr-1',
  task_id: 't1',
  exact_action: { tool: 'gmail.send', args: { to: 'bob@corp.com', body: 'hello' } },
  arg_sources: { to: 'typed by user', body: 'untrusted from tool_output' },
  action_hash: 'abcdef0123456789abcdef',
  expires_at: new Date(Date.now() + 5 * 60_000).toISOString(),
};

describe('StepList', () => {
  it('renders nothing when empty', () => {
    const { container } = render(<StepList steps={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('numbers steps by position regardless of backend index base, and shows done state', () => {
    render(
      <StepList
        steps={[
          { index: 1, title: 'First', status: 'completed' },
          { index: 2, title: 'Second', status: 'running' },
        ]}
      />
    );
    expect(screen.getByText('✓')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });
});

describe('StepList failed state', () => {
  it('shows a failed step distinctly from completed', () => {
    render(<StepList steps={[{ index: 1, title: 'Step 1', status: 'failed' }]} />);
    expect(screen.getByText('✗')).toBeInTheDocument();
    expect(screen.queryByText('✓')).not.toBeInTheDocument();
  });
});

describe('ToolCallCard', () => {
  const base = { callId: 'call-1', tool: 'gmail.read', args: { message_id: 'm1' }, argSources: { message_id: 'user' } };

  it('shows the sanitized output field from the backend', () => {
    render(
      <ToolCallCard
        {...base}
        output={{ call_id: 'call-1', tool: 'gmail.read', sanitized_output: 'clean text', scan: { disposition: 'sanitized', fields: [] } as any }}
      />
    );
    expect(screen.getByText('clean text')).toBeInTheDocument();
    expect(screen.getByText(/Disposition: sanitized/)).toBeInTheDocument();
  });

  it('shows the DENY badge and reason text, never output', () => {
    render(
      <ToolCallCard
        {...base}
        tool="gmail.send"
        decision={{ call_id: 'call-1', decision: 'DENY', reasons: ['TOOL_PROHIBITED'], reason_text: 'Denied by gateway' } as any}
      />
    );
    expect(screen.getByText('DENY')).toBeInTheDocument();
    expect(screen.getByText('Denied by gateway')).toBeInTheDocument();
    expect(screen.queryByText(/Sanitized Tool Result/)).not.toBeInTheDocument();
  });

  it('renders untrusted text as plain text, not HTML', () => {
    const evil = '<img src=x onerror="alert(1)"><script>alert(1)</script>';
    const { container } = render(
      <ToolCallCard
        {...base}
        output={{ call_id: 'call-1', tool: 'gmail.read', sanitized_output: evil, scan: { disposition: 'pass', fields: [] } as any }}
      />
    );
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText(evil)).toBeInTheDocument();
  });
});

describe('ApprovalModal', () => {
  it('renders nothing without an approval, then renders when one arrives (hook order)', () => {
    const { rerender, container } = render(<ApprovalModal approval={null} onApprove={vi.fn()} onDeny={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ApprovalModal approval={approval} onApprove={vi.fn()} onDeny={vi.fn()} />);
    expect(screen.getByText('gmail.send')).toBeInTheDocument();
    rerender(<ApprovalModal approval={null} onApprove={vi.fn()} onDeny={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the exact action with the source of each argument', () => {
    render(<ApprovalModal approval={approval} onApprove={vi.fn()} onDeny={vi.fn()} />);
    expect(screen.getByText('bob@corp.com')).toBeInTheDocument();
    expect(screen.getByText(/Source: typed by user/)).toBeInTheDocument();
    expect(screen.getByText(/Source: untrusted from tool_output/)).toBeInTheDocument();
  });

  it('approve sends no edited args when unchanged', async () => {
    const onApprove = vi.fn();
    render(<ApprovalModal approval={approval} onApprove={onApprove} onDeny={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: /Approve & Execute/ }));
    expect(onApprove).toHaveBeenCalledWith('appr-1', undefined);
  });

  it('deny calls onDeny with the approval id', async () => {
    const onDeny = vi.fn();
    render(<ApprovalModal approval={approval} onApprove={vi.fn()} onDeny={onDeny} />);
    await userEvent.click(screen.getByRole('button', { name: /Deny/ }));
    expect(onDeny).toHaveBeenCalledWith('appr-1');
  });

  it('editing an arg warns the approval is voided and submits edited args for re-approval', async () => {
    const onApprove = vi.fn();
    render(<ApprovalModal approval={approval} onApprove={onApprove} onDeny={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: /Edit Arguments/ }));
    const box = screen.getAllByRole('textbox')[0];
    await userEvent.clear(box);
    await userEvent.type(box, 'eve@corp.com');
    expect(screen.getByText(/will void cryptographic hash/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Submit for Re-Approval/ }));
    expect(onApprove).toHaveBeenCalledWith('appr-1', expect.objectContaining({ to: 'eve@corp.com' }));
  });

  it('disables Approve when the countdown reaches zero', () => {
    vi.useFakeTimers();
    try {
      const soon = { ...approval, expires_at: new Date(Date.now() + 3000).toISOString() };
      render(<ApprovalModal approval={soon} onApprove={vi.fn()} onDeny={vi.fn()} />);
      const btn = screen.getByRole('button', { name: /Approve & Execute/ });
      expect(btn).toBeEnabled();
      act(() => {
        vi.advanceTimersByTime(4000);
      });
      expect(btn).toBeDisabled();
    } finally {
      vi.useRealTimers();
    }
  });
});
