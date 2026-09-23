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

test('@v2 knowledge with no matching document states the lack of evidence', async ({ page }) => {
  const query = '知识检索：银河望远镜数值'
  const lookup = await page.request.get('/api/knowledge/search', { params: { query } })
  expect(lookup.status()).toBe(200)
  expect((await lookup.json()).data.matches).toEqual([])
  await page.goto('/agent')
  await page.getByLabel('问题', { exact: true }).fill(query)
  await page.getByRole('button', { name: '发送任务' }).click()
  await expect(page.getByTestId('run-status')).toContainText('已完成', { timeout: 12000 })
  await expect(page.getByText('本次检索没有适用的知识依据，无法据此提供排查结论。', { exact: false })).toBeVisible()
  await expect(page.getByTestId('knowledge-sources')).toHaveCount(0)
})

test('@v2 knowledge source HTML is displayed as text and never executed', async ({ page }) => {
  // Fetch the real stored source first; inject hostile text only at the browser trust boundary.
  await page.route('**/api/knowledge/sources/*/versions/*', async route => {
    const response = await route.fetch()
    expect(response.status()).toBe(200)
    const value = await response.json()
    const hostile = '<img src=x onerror="window.knowledgeExecuted=true"><script>window.knowledgeExecuted=true</script>'
    value.data.title = hostile
    value.data.content = hostile
    for (const chunk of value.data.chunks) chunk.content = hostile
    await route.fulfill({ response, json: value })
  })
  await page.goto('/agent')
  await page.getByLabel('问题', { exact: true }).fill('知识检索：平均分配 equal 的规则')
  await page.getByRole('button', { name: '发送任务' }).click()
  await expect(page.getByTestId('run-status')).toContainText('已完成', { timeout: 12000 })
  const sources = page.getByTestId('knowledge-sources')
  await sources.getByRole('button', { name: '查看来源原文' }).first().click()
  await expect(sources.getByTestId('source-content').first()).toContainText('<img src=x')
  await expect(sources.locator('img, script')).toHaveCount(0)
  expect(await page.evaluate(() => Reflect.get(window, 'knowledgeExecuted'))).toBeUndefined()
})
