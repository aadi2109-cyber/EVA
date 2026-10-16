import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../src/api/client', () => ({
  api: {
    admin: {
      getConfig: vi.fn(),
      getAudit: vi.fn(),
      proposeConfig: vi.fn(),
      approveProposal: vi.fn(),
      getReviewQueue: vi.fn(),
      recordReviewDecision: vi.fn(),
    },
  },
}));

import { api } from '../src/api/client';
import { ConfigProposals } from '../src/components/admin/ConfigProposals';
import { ReviewQueue } from '../src/components/admin/ReviewQueue';

const admin = api.admin as unknown as Record<string, ReturnType<typeof vi.fn>>;

const CONFIG = { version: 1, minimum_detector_posture: 'tier2_required', failure_mode: 'fail_closed', block_threshold: 0.85, t3_enabled: true, align_enabled: true };
const proposed = (id: string, by: string) => ({
  id: `evt-${id}`, ts: '2026-01-01T00:00:00Z', task_id: id, type: 'config.proposed', actor: `admin:${by}`,
  payload: { changes: { failure_mode: 'tier1_only_warning' }, justification: 'relax' }, config_version: 1, prev_hash: '', hash: '',
});
const changed = (id: string) => ({ ...proposed(id, 'x'), id: `evt-c-${id}`, type: 'config.changed' });

function auditFor(rows: { proposed?: any[]; changed?: any[] }) {
  admin.getAudit.mockImplementation(async ({ eventType }: { eventType: string }) =>
    eventType === 'config.proposed' ? rows.proposed ?? [] : rows.changed ?? []
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  admin.getConfig.mockResolvedValue(CONFIG);
  admin.getReviewQueue.mockResolvedValue([]);
});

describe('ConfigProposals (four-eyes)', () => {
  it('the proposer cannot approve their own proposal; sees a waiting note instead', async () => {
    auditFor({ proposed: [proposed('prop-1', 'admin-A')] });
    render(<ConfigProposals currentAdminId="admin-A" />);
    expect(await screen.findByText(/Waiting for a different admin/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Approve as second admin/ })).not.toBeInTheDocument();
  });

  it('a different admin can approve, and the call is made with the proposal id', async () => {
    auditFor({ proposed: [proposed('prop-1', 'admin-A')] });
    admin.approveProposal.mockResolvedValue({});
    render(<ConfigProposals currentAdminId="admin-B" />);
    await userEvent.click(await screen.findByRole('button', { name: /Approve as second admin/ }));
    expect(admin.approveProposal).toHaveBeenCalledWith('prop-1');
    expect(await screen.findByRole('status')).toHaveTextContent('prop-1 approved and applied');
  });

  it('proposals already applied are shown as approved with no action', async () => {
    auditFor({ proposed: [proposed('prop-1', 'admin-A')], changed: [changed('prop-1')] });
    render(<ConfigProposals currentAdminId="admin-B" />);
    expect(await screen.findByText('approved')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Approve as second admin/ })).not.toBeInTheDocument();
  });

  it('surfaces the guard error verbatim when approval is rejected', async () => {
    auditFor({ proposed: [proposed('prop-1', 'admin-A')] });
    admin.approveProposal.mockRejectedValue(new Error('Four-eyes rule violation'));
    render(<ConfigProposals currentAdminId="admin-B" />);
    await userEvent.click(await screen.findByRole('button', { name: /Approve as second admin/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Four-eyes rule violation');
  });

  it('submits only changed fields, and only with a justification', async () => {
    auditFor({});
    admin.proposeConfig.mockResolvedValue({ proposal_id: 'prop-9' });
    render(<ConfigProposals currentAdminId="admin-A" />);
    const submit = await screen.findByRole('button', { name: 'Submit proposal' });
    expect(submit).toBeDisabled();

    await userEvent.selectOptions(screen.getByLabelText('Failure mode'), 'tier1_only_warning');
    expect(submit).toBeDisabled(); // still no justification
    await userEvent.type(screen.getByLabelText(/Justification/), 'needed for demo');
    expect(submit).toBeEnabled();
    await userEvent.click(submit);

    expect(admin.proposeConfig).toHaveBeenCalledWith({ failure_mode: 'tier1_only_warning' }, 'needed for demo');
    expect(await screen.findByRole('status')).toHaveTextContent('different admin must approve');
  });
});

describe('ReviewQueue', () => {
  it('shows the empty state', async () => {
    render(<ReviewQueue reviewerId="admin-A" />);
    expect(await screen.findByText('The review queue is empty.')).toBeInTheDocument();
  });

  it('requires notes, then records the decision with the reviewer id', async () => {
    admin.getReviewQueue.mockResolvedValue([{ id: 'item-1', created_at: 'x' }]);
    admin.recordReviewDecision.mockResolvedValue({ status: 'recorded', item: {} });
    render(<ReviewQueue reviewerId="admin-A" />);
    await userEvent.click(await screen.findByRole('button', { name: /PENDING/ }));

    const record = screen.getByRole('button', { name: 'Record decision' });
    expect(record).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText('Decision'), 'rejected');
    await userEvent.type(screen.getByLabelText(/Notes/), 'phishing');
    await userEvent.click(record);

    expect(admin.recordReviewDecision).toHaveBeenCalledWith('item-1', 'admin-A', 'rejected', 'phishing');
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('recorded for item-1'));
  });

  it('renders item fields as plain text', async () => {
    const evil = '<img src=x onerror=alert(1)>';
    admin.getReviewQueue.mockResolvedValue([{ id: 'item-2', source: evil }]);
    const { container } = render(<ReviewQueue reviewerId="admin-A" />);
    expect(await screen.findByText(`source: ${evil}`)).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
  });
});
