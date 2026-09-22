import { test, expect } from '@playwright/test'
import { writeFile } from 'node:fs/promises'

test('三设备与真实场景切换、离线恢复', async ({ page }, info) => {
  await page.goto('/devices')
  await expect(page.getByRole('heading', { name: '设备总览' })).toBeVisible()
  await expect(page.getByTestId('device-card')).toHaveCount(3)
  await page.getByRole('link', { name: '查看 CHG-002' }).click()
  await expect(page.getByRole('heading', { name: 'CHG-002' })).toBeVisible()
  await page.getByRole('button', { name: '模拟过温' }).click()
  await expect(page.getByTestId('command-status')).toContainText('已应用', { timeout: 8000 })
  await expect(page.getByTestId('device-health')).toContainText('过温', { timeout: 8000 })
  await page.evaluate(() => {
    const stamps: Record<string, number> = {}
    Object.assign(window, { scenarioStamps: stamps })
    new MutationObserver(() => {
      const text = document.querySelector('[data-testid="device-connection"]')?.textContent
      if (text?.includes('离线') && !stamps.offline) stamps.offline = Date.now()
      if (text?.includes('在线') && stamps.offline && !stamps.recovered) stamps.recovered = Date.now()
    }).observe(document.body, { subtree: true, childList: true, characterData: true })
  })
  await page.getByRole('button', { name: '暂停上报' }).click()
  await expect(page.getByTestId('command-status')).toContainText('等待离线判定', { timeout: 8000 })
  await expect(page.getByTestId('device-connection')).toContainText('离线', { timeout: 19000 })
  const offline = (await (await page.request.get('/api/devices/CHG-002')).json()).data
  const normalCommand = page.waitForResponse(response => response.url().endsWith('/api/simulator/scenarios') && response.request().method() === 'POST')
  await page.getByRole('button', { name: '恢复正常' }).click()
  const commandId = (await (await normalCommand).json()).data.command_id
  await expect(page.getByTestId('device-connection')).toContainText('在线', { timeout: 8000 })
  await expect(page.getByTestId('device-health')).toContainText('正常', { timeout: 8000 })
  const command = (await (await page.request.get(`/api/simulator/commands/${commandId}`)).json()).data
  const stamps = await page.evaluate(() => (window as unknown as { scenarioStamps: Record<string, number> }).scenarioStamps)
  const timings = { offline_ms: stamps.offline - Date.parse(offline.last_live_received_at), recovery_ms: stamps.recovered - Date.parse(command.ack_at) }
  await writeFile(info.outputPath('scenario-timings.json'), JSON.stringify(timings, null, 2))
  await info.attach('scenario-timings.json', { body: JSON.stringify(timings), contentType: 'application/json' })
  expect(timings.offline_ms).toBeGreaterThan(15000)
  expect(timings.offline_ms).toBeLessThanOrEqual(18000)
  expect(timings.recovery_ms).toBeGreaterThanOrEqual(0)
  expect(timings.recovery_ms).toBeLessThanOrEqual(4000)
  await expect(page.getByTestId('telemetry-chart')).not.toHaveAttribute('data-gap-count', '0')
  for (const minutes of ['30', '60', '10']) {
    const response = page.waitForResponse(response => response.url().includes('/CHG-002/telemetry?'))
    await page.getByLabel('历史窗口').selectOption(minutes)
    const result = await response
    const params = new URL(result.url()).searchParams
    expect(Date.parse(params.get('to')!) - Date.parse(params.get('from')!)).toBe(Number(minutes) * 60000)
  }
})

for (const width of [1280, 1920]) {
  test(`布局与截图 ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: width === 1280 ? 720 : 1080 })
    await page.goto('/devices')
    await expect(page.getByTestId('device-card')).toHaveCount(3)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.screenshot({ path: info.outputPath(`devices-${width}.png`), fullPage: true })
    await page.goto('/devices/CHG-002')
    await expect(page.getByTestId('device-health')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.screenshot({ path: info.outputPath(`detail-${width}.png`), fullPage: true })
    await page.goto('/agent')
    await expect(page.getByRole('heading', { name: 'Agent 助手' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.screenshot({ path: info.outputPath(`agent-${width}.png`), fullPage: true })
  })
}

test('未知设备和服务断开可见', async ({ page }, info) => {
  await page.goto('/devices/CHG-999')
  await expect(page.getByRole('alert')).toContainText('设备不存在')
  await page.screenshot({ path: info.outputPath('unknown-device.png'), fullPage: true })
  await page.route('**/api/devices', route => route.abort())
  await page.goto('/devices')
  await expect(page.getByRole('alert')).toContainText('服务连接失败')
  await page.screenshot({ path: info.outputPath('service-disconnected.png'), fullPage: true })
})

test('来回切页十次取消旧轮询，同一查询不重叠', async ({ page }) => {
  const active = new Map<string, number>(), maximum = new Map<string, number>()
  const key = (url: string) => new URL(url).pathname
  page.on('request', request => {
    if (!request.url().includes('/api/devices')) return
    const path = key(request.url()), value = (active.get(path) || 0) + 1
    active.set(path, value); maximum.set(path, Math.max(maximum.get(path) || 0, value))
  })
  const finish = (url: string) => { if (url.includes('/api/devices')) { const path = key(url); active.set(path, (active.get(path) || 1) - 1) } }
  page.on('requestfinished', request => finish(request.url()))
  page.on('requestfailed', request => finish(request.url()))
  await page.goto('/devices')
  for (let i = 0; i < 10; i++) {
    await page.getByRole('link', { name: '查看 CHG-002' }).click()
    await expect(page.getByRole('heading', { name: 'CHG-002' })).toBeVisible()
    await page.getByRole('link', { name: '返回设备总览' }).click()
    await expect(page.getByTestId('device-card')).toHaveCount(3)
  }
  await page.getByRole('link', { name: /Agent 助手/ }).click()
  let oldPolls = 0
  page.on('request', request => { if (request.url().includes('/api/devices')) oldPolls++ })
  await page.waitForTimeout(2500)
  expect(oldPolls).toBe(0)
  expect(Math.max(...maximum.values())).toBe(1)
})

test('离开详情时未完成的场景请求不能重启旧轮询', async ({ page }) => {
  let release: (() => void) | undefined
  const held = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/simulator/scenarios', async route => {
    const response = await route.fetch()
    await held
    await route.fulfill({ response }).catch(() => {})
  })
  await page.goto('/devices/CHG-002')
  await page.getByRole('button', { name: '恢复正常' }).click()
  await page.getByRole('link', { name: '返回设备总览' }).click()
  await expect(page.getByTestId('device-card')).toHaveCount(3)
  let oldRequests = 0
  page.on('request', request => { if (request.url().includes('/api/simulator/commands/')) oldRequests++ })
  release?.()
  await page.waitForTimeout(1500)
  expect(oldRequests).toBe(0)
})
