import { test, expect } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { execFileSync } from 'node:child_process'

test('@v2 lost device ACK leaves the power plan partial and budget unconfirmed', async ({ page }) => {
  test.setTimeout(90000)
  const project = process.env.E2E_COMPOSE_PROJECT || ''
  expect(project).toMatch(/^charge-smoke-[a-f0-9]+$/)
  for (const device of ['CHG-001', 'CHG-002', 'CHG-003']) {
    const accepted = await page.request.post(`/api/devices/${device}/charging/start`, { data: { request_id: randomUUID(), requested_power_w: 10000 } })
    expect(accepted.status()).toBe(202)
    const id = (await accepted.json()).data.command_id
    await expect.poll(async () => (await (await page.request.get(`/api/device-commands/${id}`)).json()).data.verification_status, { timeout: 10000 }).toBe('verified')
  }
  await page.goto('/devices')
  await page.getByLabel('站点预算（W）').fill('15000')
  await page.getByRole('button', { name: '生成预览', exact: true }).click()
  await expect(page.getByTestId('power-plan')).toContainText('仅预览')
  const prior = (await (await page.request.get('/api/station-state')).json()).data.budget_w
  const container = `${project}-simulator-1`
  try {
    execFileSync('docker', ['stop', '--time', '1', container], { stdio: 'pipe' })
    await page.getByRole('button', { name: '执行此计划', exact: true }).click()
    await expect(page.getByTestId('power-plan')).toContainText('部分完成', { timeout: 35000 })
    await expect(page.getByTestId('power-plan')).toContainText('不能认定新预算已生效')
    await expect(page.getByTestId('power-plan')).not.toContainText('全部效果已验证')
    expect((await (await page.request.get('/api/station-state')).json()).data.budget_w).toBe(prior)
  } finally { execFileSync('docker', ['start', container], { stdio: 'pipe' }) }
})
