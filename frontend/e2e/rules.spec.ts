import { test, expect } from '@playwright/test'

test('@v2 rules use server versions and keep fixed offline threshold', async ({ page }) => {
  await page.goto('/devices/CHG-003')
  const row = page.getByTestId('alarm-rule-OVERHEAT')
  const before = (await (await page.request.get('/api/alarm-rules/CHG-003/OVERHEAT')).json()).data
  await row.getByLabel('启用过温告警').uncheck()
  await row.getByRole('button', { name: '保存规则' }).click()
  await expect(row).toContainText('规则已保存')
  const changed = (await (await page.request.get('/api/alarm-rules/CHG-003/OVERHEAT')).json()).data
  expect(changed.version).toBe(before.version + 1)
  expect(changed.enabled).toBe(false)
  await row.getByLabel('启用过温告警').check()
  await row.getByRole('button', { name: '保存规则' }).click()
  await expect.poll(async () => (await (await page.request.get('/api/alarm-rules/CHG-003/OVERHEAT')).json()).data.enabled).toBe(true)
  await expect(page.getByTestId('alarm-rule-OFFLINE')).toContainText('15 秒离线阈值不可在此修改')
})
