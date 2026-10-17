import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('../src/api/client', () => ({
  api: {
    admin: {
      getHealth: vi.fn().mockResolvedValue({ status: 'ok', tier2_available: true, t3_available: true, align_available: true, config_version: 1, contract_version: '0.1.0', kill_switch: { all_write_tools: false, tools: [] }, metrics: {} }),
      getAudit: vi.fn().mockResolvedValue([]),
      getEvalRuns: vi.fn().mockResolvedValue([]),
      getEvalSummary: vi.fn(),
      getConfig: vi.fn().mockResolvedValue({ version: 1 }),
      listProposals: vi.fn().mockResolvedValue([]),
      getReviewQueue: vi.fn().mockResolvedValue([]),
    },
  },
}));

import { api } from '../src/api/client';
import { Admin } from '../src/pages/Admin';

const user = { id: 'a1', email: 'a@x', name: 'a', role: 'admin' as const };
const summary = api.admin.getEvalSummary as unknown as ReturnType<typeof vi.fn>;

describe('Admin eval summary', () => {
  it('does not crash when the guard has no scenario runs yet (comparison_table is null)', async () => {
    summary.mockResolvedValue({ latest: { scenarios: null }, comparison_table: null, notes: ['Zero successes is not immunity.'] });
    render(<Admin currentUser={user} />);
    expect(await screen.findByText('Zero successes is not immunity.')).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: /Baseline, Basic and Full/ })).not.toBeInTheDocument();
  });

  it('renders the Baseline/Basic/Full table with em dashes for unmeasured cells', async () => {
    summary.mockResolvedValue({ latest: {}, comparison_table: [{ metric: 'clean_task_completion', baseline: 0.94, basic: null, full: 0.92 }], notes: [] });
    render(<Admin currentUser={user} />);
    const table = await screen.findByRole('table', { name: /Baseline, Basic and Full/ });
    expect(table).toHaveTextContent('clean task completion');
    expect(table).toHaveTextContent('—');
  });
});
