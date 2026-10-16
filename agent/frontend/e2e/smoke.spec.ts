import { test, expect } from '@playwright/test';
import { login, S1_EVENTS, S4_EVENTS, sendPrompt, stubApi } from './fixtures';

test('login: bad credentials show an error, good credentials reach the workspace', async ({ page }) => {
  await stubApi(page);
  await login(page, 'wrong');
  await expect(page.getByRole('alert')).toContainText('Incorrect email or password');

  await page.locator('input[type=password]').fill('good');
  await page.getByRole('button', { name: /Authenticate Session/ }).click();
  await expect(page.getByText('High-Assurance Task Workspace')).toBeVisible();
  await expect(page.getByText('ROLE: USER')).toBeVisible();
});

test('S1: injected email is sanitized and the task summary is shown', async ({ page }) => {
  await stubApi(page, { events: S1_EVENTS });
  await login(page);
  await sendPrompt(page, 'Summarize my emails and list pending invoices');

  await expect(page.getByText('gmail.read').first()).toBeVisible();
  await expect(page.getByText('ALLOW').first()).toBeVisible();
  await expect(page.getByText('Invoice #1042 due Friday.')).toBeVisible();
  await expect(page.getByText(/Disposition: sanitized/)).toBeVisible();
  await expect(page.getByText('Pending: Invoice #1042 ($1,500).')).toBeVisible();
  await expect(page.getByText(/1 sentence/)).toBeVisible();
});

test('S4: approval modal shows the exact action and Approve posts the decision', async ({ page }) => {
  const stub = await stubApi(page, { events: S4_EVENTS });
  await login(page);
  await sendPrompt(page, 'Email the report to bob@corp.com');

  const approve = page.getByRole('button', { name: /Approve & Execute/ });
  await expect(approve).toBeVisible();
  await expect(page.getByText('bob@corp.com').first()).toBeVisible();
  await expect(page.getByText(/Source: typed by user/)).toBeVisible();

  await approve.click();
  await expect(approve).toBeHidden();
  expect(stub.approvals).toHaveLength(1);
  expect(stub.approvals[0]).toEqual({ id: 'appr-1', body: { approved: true, edited_args: null } });
});

test('S7: degraded guard shows a persistent banner that side-effect tools are disabled', async ({ page }) => {
  await stubApi(page, {
    health: {
      backend: { status: 'ok' },
      guard: { status: 'degraded', tier2_available: false, t3_available: false, align_available: true, config_version: 1, contract_version: '0.1.0', kill_switch: { all_write_tools: false, tools: [] }, metrics: {} },
    },
  });
  await login(page);
  await expect(page.getByText(/Side-effect tools are disabled/i)).toBeVisible();
});
