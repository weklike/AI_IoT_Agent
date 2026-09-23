import { test, expect } from '@playwright/test'
import { randomUUID } from 'node:crypto'

test('@v2 applied ACK without telemetry remains unconfirmed after late recovery', async ({ page }, info) => {
  test.setTimeout(45000)
  let sessionId = ''
  try {
    await page.goto('/devices/CHG-001')
    await expect(page.getByRole('button', { name: '开始充电', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: '暂停上报' }).click()
    await expect(page.getByTestId('command-status')).toContainText('等待离线判定')
    const accepted = page.waitForResponse(response => response.url().endsWith('/CHG-001/charging/start') && response.request().method() === 'POST')
    await page.getByRole('button', { name: '开始充电', exact: true }).click()
    const response = await accepted
    expect(response.status()).toBe(202)
    const command = (await response.json()).data
    sessionId = command.session_id
    await expect(page.getByTestId('charging-command')).toContainText('效果未确认', { timeout: 8000 })
    await expect(page.getByTestId('charging-command')).not.toContainText('效果已验证')
    const before = (await (await page.request.get(`/api/device-commands/${command.command_id}`)).json()).data
    expect(before.status).toBe('applied')
    expect(before.verification_status).toBe('unconfirmed')
    await page.getByRole('button', { name: '恢复正常' }).click()
    await expect.poll(async () => (await (await page.request.get('/api/devices/CHG-001')).json()).data.session_id, { timeout: 7000 }).toBe(sessionId)
    const after = (await (await page.request.get(`/api/device-commands/${command.command_id}`)).json()).data
    expect(after.verification_status).toBe('unconfirmed')
    await expect(page.getByTestId('charging-command')).toContainText('效果未确认')
    await info.attach('actual-command-before-after.json', { body: JSON.stringify({ before, after }, null, 2), contentType: 'application/json' })
    await page.screenshot({ path: info.outputPath('applied-unconfirmed.png'), fullPage: true })
  } finally {
    await page.request.post('/api/simulator/scenarios', { data: { device_id: 'CHG-001', scenario: 'normal' } })
    if (sessionId) {
      const response = await page.request.post('/api/devices/CHG-001/charging/stop', { data: { request_id: randomUUID(), session_id: sessionId } })
      expect(response.status()).toBe(202)
      const commandId = (await response.json()).data.command_id
      await expect.poll(async () => (await (await page.request.get(`/api/device-commands/${commandId}`)).json()).data.verification_status, { timeout: 10000 }).toBe('verified')
    }
  }
})
