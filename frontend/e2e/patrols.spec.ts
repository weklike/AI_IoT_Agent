import { test, expect } from '@playwright/test'

test('@v2 patrol uses real fleet facts and refresh restores the same report', async ({ page }) => {
  await page.goto('/devices')
  await expect(page.getByRole('button', { name: '一键巡检', exact: true })).toBeVisible()
  const accepted = page.waitForResponse(response => response.url().endsWith('/api/patrols') && response.request().method() === 'POST')
  await page.getByRole('button', { name: '一键巡检', exact: true }).click()
  const { report_id, run_id } = (await (await accepted).json()).data
  await expect(page.getByTestId('patrol-summary')).toContainText('已完成', { timeout: 12000 })
  const report = (await (await page.request.get(`/api/patrols/${report_id}`)).json()).data
  const run = (await (await page.request.get(`/api/agent/runs/${run_id}`)).json()).data
  expect(run.allow_work_order).toBe(false)
  expect(run.tool_calls[0].tool_name).toBe('get_fleet_overview')
  expect(report.snapshot_json.devices).toHaveLength(3)
  let newRuns = 0
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/api/patrols')) newRuns++ })
  await page.reload()
  await expect(page.getByTestId('patrol-summary')).toContainText(report_id)
  expect(newRuns).toBe(0)
  await page.getByRole('link', { name: '查看巡检报告', exact: true }).click()
  await expect(page.getByRole('heading', { name: '巡检报告', exact: true })).toBeVisible()
  for (const device of report.snapshot_json.devices) {
    const fact = page.getByTestId(`patrol-fact-${device.device_id}`)
    await expect(fact).toContainText(`${device.statistics.sample_count} 条样本`)
  }
})
