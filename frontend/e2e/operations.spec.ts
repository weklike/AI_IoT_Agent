import { test, expect } from '@playwright/test'

test('@v2 charging begins at zero then receives a verified power allocation', async ({ page }) => {
  test.setTimeout(90000)
  await page.goto('/devices/CHG-001')
  await expect(page.getByRole('heading', { name: '充电运行' })).toBeVisible()
  await page.getByLabel('请求功率（W）').fill('10000')
  await page.getByRole('button', { name: '开始充电', exact: true }).click()
  await expect(page.getByTestId('charging-command')).toContainText('效果已验证', { timeout: 12000 })
  await expect(page.getByTestId('charging-runtime')).toContainText('等待功率分配')
  const before = (await (await page.request.get('/api/devices/CHG-001')).json()).data
  expect(before.power_limit_w).toBe(0)
  expect(before.session_state).toBe('ACTIVE')
  await page.goto('/devices')
  await page.getByLabel('站点预算（W）').fill('10000')
  await page.getByRole('button', { name: '生成预览', exact: true }).click()
  await expect(page.getByTestId('power-plan')).toContainText('仅预览')
  const previewed = (await (await page.request.get('/api/devices/CHG-001')).json()).data
  expect(previewed.power_limit_w).toBe(0)
  await page.getByRole('button', { name: '执行此计划', exact: true }).click()
  await expect(page.getByTestId('power-plan')).toContainText('全部效果已验证', { timeout: 35000 })
  await page.goto('/devices/CHG-001')
  await expect(page.getByTestId('charging-runtime')).toContainText('10000 W', { timeout: 7000 })
  await page.getByRole('button', { name: '停止充电', exact: true }).click()
  await expect(page.getByTestId('charging-command')).toContainText('效果已验证', { timeout: 12000 })
  await expect(page.getByTestId('session-list')).toContainText('COMPLETED', { timeout: 7000 })
  await expect(page.getByTestId('event-timeline')).toContainText('会话报告', { timeout: 7000 })
})
