import { test, expect } from '@playwright/test'

test('@v2 knowledge displays actual searched source version and original chunk', async ({ page }) => {
  await page.goto('/agent')
  await page.getByLabel('问题', { exact: true }).fill('知识检索：平均分配 equal 的规则')
  await page.getByRole('button', { name: '发送任务' }).click()
  await expect(page.getByTestId('run-status')).toContainText('已完成', { timeout: 12000 })
  const sources = page.getByTestId('knowledge-sources')
  await expect(sources).toContainText('KB-POWER-01')
  await sources.getByRole('button', { name: '查看来源原文' }).first().click()
  await expect(sources).toContainText('authored_simulation')
  await expect(sources.getByTestId('source-content').first()).toContainText('平均分配')
})
