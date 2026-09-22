import { test, expect } from '@playwright/test'

test('查询不建单，刷新恢复服务器轨迹', async ({ page }) => {
  await page.goto('/agent')
  await expect(page.getByText('fixture · 替身模型')).toBeVisible()
  await page.getByLabel('问题').fill('查询2号桩当前状态')
  await page.getByRole('button', { name: '发送任务' }).click()
  await expect(page.getByTestId('run-status')).toHaveText('已完成', { timeout: 10000 })
  await expect(page.getByTestId('tool-trace')).toContainText('get_device_status')
  await expect(page.getByTestId('tool-trace')).not.toContainText('create_work_order')
  const before = await page.getByTestId('run-id').textContent()
  await page.reload()
  await expect(page.getByTestId('run-status')).toHaveText('已完成')
  expect(await page.getByTestId('run-id').textContent()).toEqual(before)
})

test('授权建单后重复查询只显示真实工单', async ({ page }) => {
  await page.goto('/devices/CHG-002')
  await page.getByRole('button', { name: '模拟过温' }).click()
  await expect(page.getByTestId('device-health')).toContainText('过温', { timeout: 8000 })
  await page.goto('/agent')
  await page.getByLabel('问题').fill('检查2号桩过温并创建检修工单')
  await page.getByLabel('允许本次创建检修工单').check()
  await page.getByRole('button', { name: '发送任务' }).click()
  await expect(page.getByTestId('run-status')).toHaveText('已完成', { timeout: 10000 })
  await expect(page.getByTestId('tool-trace')).toContainText('create_work_order')
  await expect(page.getByTestId('work-orders')).toContainText('OVERHEAT')
})

test('响应丢失后重试使用原 request_id，终态停止轮询', async ({ page }) => {
  const requests: string[] = []
  let originalRun = ''
  await page.route('**/api/agent/runs', async route => {
    requests.push(route.request().postDataJSON().request_id)
    const response = await route.fetch()
    originalRun = (await response.json()).data.run_id
    if (requests.length === 1) await route.abort()
    else await route.fulfill({ response })
  })
  await page.goto('/agent')
  await page.getByLabel('问题').fill('查询1号桩当前状态')
  await page.getByRole('button', { name: '发送任务' }).evaluate((button: HTMLButtonElement) => { button.click(); button.click() })
  await expect(page.getByRole('alert')).toContainText('复用原请求重试')
  expect(requests).toHaveLength(1)
  await page.reload()
  await page.getByRole('button', { name: '重试原请求' }).click()
  await expect(page.getByTestId('run-status')).toHaveText('已完成')
  expect(requests).toHaveLength(2)
  expect(requests[0]).toBe(requests[1])
  await expect(page.getByTestId('run-id')).toHaveText(originalRun)
  let polls = 0
  page.on('request', request => { if (request.url().includes('/api/agent/runs/')) polls++ })
  await page.waitForTimeout(2200)
  expect(polls).toBe(0)
})

test('未知设备任务显示失败及真实错误轨迹', async ({ page }, info) => {
  await page.goto('/agent')
  await page.getByLabel('问题').fill('查询999号桩当前状态')
  await page.getByRole('button', { name: '发送任务' }).click()
  await expect(page.getByTestId('run-status')).toHaveText('执行失败')
  await expect(page.getByTestId('tool-trace')).toContainText('失败')
  await expect(page.getByText('DEVICE_NOT_FOUND').first()).toBeVisible()
  await page.screenshot({ path: info.outputPath('unknown-device.png'), fullPage: true })
})
