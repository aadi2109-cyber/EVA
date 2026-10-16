import { describe, it, expect } from 'vitest';
import { SCENARIOS } from '../src/mocks/mockStream';

describe('mock scenarios', () => {
  it.each(['S1', 'S2', 'S4', 'S7'])('%s is defined with ordered events ending in a terminal event', (id) => {
    const evs = SCENARIOS[id].events;
    expect(evs.length).toBeGreaterThan(0);
    expect(['task.completed', 'task.held', 'task.failed', 'task.cancelled', 'approval.required']).toContain(
      evs[evs.length - 1].event
    );
  });

  it('S4 includes an approval request with an action hash', () => {
    const a = SCENARIOS.S4.events.find((e) => e.event === 'approval.required');
    expect((a!.data as any).approval.action_hash).toBeTruthy();
  });
});
