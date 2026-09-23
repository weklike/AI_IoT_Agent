import { test, expect } from '@playwright/test'
import { randomUUID } from 'node:crypto'

for (const failure of ['disconnect', 'server-error']) {
test(`@v2 lost charging response ${failure} survives refresh and retries the original request`, async ({ page }) => {
  test.setTimeout(45000)
  const requests: string[] = []
  let sessionId = ''
  await page.route('**/api/devices/CHG-003/charging/start', async route => {
    requests.push(route.request().postDataJSON().request_id)
    if (requests.length === 1) {
      const response = await route.fetch()
      expect(response.status()).toBe(202)
      sessionId = (await response.json()).data.session_id
      if (failure === 'disconnect') await route.abort('connectionreset')
      else await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'DATABASE_UNAVAILABLE', message: '测试响应中断：操作结果未确认' } }) })
    } else await route.continue()
  })
  try {
    await page.goto('/devices/CHG-003')
    await expect(page.getByRole('button', { name: '开始充电', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: '开始充电', exact: true }).click()
    await expect(page.getByRole('button', { name: '重试原充电请求', exact: true })).toBeVisible()
    await page.reload()
    await page.getByRole('button', { name: '重试原充电请求', exact: true }).click()
    await expect(page.getByTestId('charging-command')).toContainText('效果已验证', { timeout: 12000 })
    expect(requests).toHaveLength(2)
    expect(requests[0]).toBe(requests[1])
    const state = (await (await page.request.get('/api/devices/CHG-003')).json()).data
    expect(state.session_id).toBe(sessionId)
  } finally {
    if (sessionId) {
      const response = await page.request.post('/api/devices/CHG-003/charging/stop', { data: { request_id: randomUUID(), session_id: sessionId } })
      if (response.status() === 202) {
        const command = (await response.json()).data.command_id
        await expect.poll(async () => (await (await page.request.get(`/api/device-commands/${command}`)).json()).data.verification_status, { timeout: 10000 }).toBe('verified')
      }
    }
  }
})

}
