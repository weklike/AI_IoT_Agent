import { test, expect } from '@playwright/test'
test('@empty 空库显示未知状态与空历史', async ({ page }, info) => {
  await page.goto('/devices/CHG-001')
  await expect(page.getByTestId('device-connection')).toContainText('状态未知')
  await expect(page.getByText('该窗口暂无历史样本')).toBeVisible()
  await page.screenshot({ path: info.outputPath('empty-history.png'), fullPage: true })
  await page.goto('/agent')
  await page.getByLabel('问题').fill('查询1号桩当前状态')
  await page.getByRole('button', { name: '发送任务' }).click()
  await expect(page.getByTestId('run-status')).toHaveText('执行失败')
  await expect(page.getByText('NO_DATA').first()).toBeVisible()
})
