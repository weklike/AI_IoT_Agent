import { test, expect } from '@playwright/test'

test('@v2 script refresh restores its record and explicit cancellation stops it', async ({ page }) => {
  await page.goto('/devices/CHG-003')
  await expect(page.getByRole('heading', { name: '固定场景脚本' })).toBeVisible()
  const accepted = page.waitForResponse(response => response.url().endsWith('/api/simulator/scripts') && response.request().method() === 'POST')
  await page.getByRole('button', { name: '运行60秒脚本', exact: true }).click()
  const id = (await (await accepted).json()).data.script_id
  await expect(page.getByTestId('script-status')).toContainText('运行中')
  await page.reload()
  await expect(page.getByTestId('script-status')).toContainText(id)
  await page.getByRole('button', { name: '取消剩余步骤', exact: true }).click()
  await expect(page.getByTestId('script-status')).toContainText('已取消')
  const result = (await (await page.request.get(`/api/simulator/scripts/${id}`)).json()).data
  expect(result.status).toBe('cancelled')
  expect(result.steps_json).toHaveLength(1)
})
