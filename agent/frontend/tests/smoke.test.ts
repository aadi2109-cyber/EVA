/**
 * Frontend Contracts & Smoke Test Suite
 */

import { SCENARIOS } from '../src/mocks/mockStream';

export function testContracts() {
  console.log('Validating EVA Frontend Scenarios & Contracts...');

  const requiredScenarios = ['S1', 'S2', 'S4', 'S7'];
  for (const sId of requiredScenarios) {
    if (!SCENARIOS[sId]) {
      throw new Error(`Missing required scenario ${sId}`);
    }
    if (SCENARIOS[sId].events.length === 0) {
      throw new Error(`Scenario ${sId} has no events`);
    }
  }

  console.log('✓ All 4 core scenarios (S1, S2, S4, S7) defined and populated.');
  return true;
}

if (typeof process !== 'undefined' && process.argv && process.argv[1]?.includes('smoke.test.ts')) {
  testContracts();
}
