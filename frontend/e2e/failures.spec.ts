import { test, expect } from '@playwright/test'
for (const kind of ['工具', '模型']) {
  test(`@failure ${kind}超时显示终态`, async ({ page }, info) => {
    await page.goto('/agent')
    await page.getByLabel('问题').fill(`测试${kind}超时`)
    await page.getByRole('button', { name: '发送任务' }).click()
    if (kind === '模型') {
      await expect(page.getByTestId('run-status')).toHaveText('执行中')
      const id = await page.getByTestId('run-id').textContent()
      await page.reload()
      await expect(page.getByTestId('run-id')).toHaveText(id!)
    }
    await expect(page.getByTestId('run-status')).toHaveText('执行超时', { timeout: 25000 })
    await expect(page.getByRole('button', { name: '开始新任务' })).toBeVisible()
    await page.screenshot({ path: info.outputPath(`${kind}-timeout.png`), fullPage: true })
  })
}

test('@failure 未授权建单只显示提示', async ({ page }, info) => {
  await page.goto('/agent')
  await page.getByLabel('问题').fill('给2号桩建个过温工单')
  await page.getByRole('button', { name: '发送任务' }).click()
  // The fixture must query the actual status but never exposes the write tool.
  await expect(page.getByTestId('run-status')).toHaveText('已完成')
  await expect(page.getByText('本次未授权创建工单', { exact: false })).toBeVisible()
  await expect(page.getByTestId('tool-trace')).not.toContainText('create_work_order')
  await page.screenshot({ path: info.outputPath('write-not-allowed.png'), fullPage: true })
})
