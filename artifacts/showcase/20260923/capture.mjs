import { createRequire } from 'node:module'
import fs from 'node:fs'
const require = createRequire(`${process.cwd()}/frontend/package.json`)
const { chromium, expect } = require('@playwright/test')
const out = 'artifacts/showcase/20260923'
const { url } = JSON.parse(fs.readFileSync(`${out}/instance.json`, 'utf8'))
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } })
const page = await context.newPage()
const errors = []
page.on('pageerror', e => errors.push(e.message))
const records = { url, mode: 'fixture', created_at: new Date().toISOString(), actions: [] }
try {
  for (const id of ['CHG-001', 'CHG-002', 'CHG-003']) {
    await page.goto(`${url}/devices/${id}`)
    const current = (await (await page.request.get(`${url}/api/devices/${id}`)).json()).data
    if (current.session_state === 'ACTIVE') { records.actions.push({ device: id, action: 'resume existing showcase session', result: 'ACTIVE' }); continue }
    await expect(page.getByRole('button', { name: '开始充电', exact: true })).toBeEnabled({ timeout: 15000 })
    await page.getByLabel('请求功率（W）').fill('20000')
    await page.getByRole('button', { name: '开始充电', exact: true }).click()
    await expect(page.getByTestId('charging-command')).toContainText('效果已验证', { timeout: 15000 })
    records.actions.push({ device: id, action: 'start', result: 'verified' })
  }
  await page.goto(`${url}/devices`)
  await expect(page.getByRole('region', { name: '运维功能导览' })).toBeVisible()
  await page.getByRole('link', { name: /02 \/ DISPATCH/ }).click()
  await expect(page.getByRole('heading', { name: '站点功率分配', exact: true })).toBeInViewport()
  await page.getByLabel('站点预算（W）').fill('45000')
  await page.getByRole('button', { name: '生成预览', exact: true }).click()
  await expect(page.getByTestId('power-plan')).toContainText('仅预览')
  await page.getByRole('button', { name: '执行此计划', exact: true }).click()
  await expect(page.getByTestId('power-plan')).toContainText('全部效果已验证', { timeout: 35000 })
  await page.locator('#station-power').screenshot({ path: `${out}/02-power-plan.png` })
  records.actions.push({ action: 'power allocation', budget_w: 45000, result: 'VERIFIED' })
  await page.goto(`${url}/devices/CHG-002`)
  await page.getByRole('button', { name: '模拟过温', exact: true }).click()
  await expect(page.getByTestId('device-health')).toContainText('过温', { timeout: 10000 })
  await expect(page.getByTestId('alarm-list')).toContainText('OVERHEAT', { timeout: 20000 })
  await page.goto(`${url}/agent`)
  await page.getByLabel('问题').fill('检查2号桩过温并创建检修工单')
  await page.getByLabel('允许本次创建检修工单').check()
  await page.getByRole('button', { name: '发送任务' }).click()
  await expect(page.getByTestId('run-status')).toHaveText('已完成', { timeout: 15000 })
  await expect(page.getByTestId('tool-trace')).toContainText('create_work_order')
  await expect(page.getByTestId('work-orders')).toContainText('OVERHEAT')
  records.agent_run_id = (await page.getByTestId('run-id').textContent()).trim()
  await page.screenshot({ path: `${out}/04-agent.png`, fullPage: true })
  await page.goto(`${url}/devices`)
  await page.getByRole('button', { name: '一键巡检', exact: true }).click()
  await expect(page.getByTestId('patrol-summary')).toContainText('已完成', { timeout: 15000 })
  await page.evaluate(() => scrollTo(0, 0))
  await page.screenshot({ path: `${out}/01-overview.png`, fullPage: false })
  await page.screenshot({ path: `${out}/01-overview-full.png`, fullPage: true })
  await page.getByRole('link', { name: '查看巡检报告', exact: true }).click()
  await expect(page.getByRole('heading', { name: '巡检报告', exact: true })).toBeVisible()
  await page.screenshot({ path: `${out}/05-patrol.png`, fullPage: true })
  records.patrol_url = page.url()
  await page.goto(`${url}/devices/CHG-002`)
  await expect(page.getByTestId('work-orders')).toContainText('OVERHEAT')
  await page.screenshot({ path: `${out}/03-device-detail.png`, fullPage: true })
  records.fleet = (await (await page.request.get(`${url}/api/fleet-overview?window_minutes=30`)).json()).data
  for (const width of [1280, 1920]) {
    await page.setViewportSize({ width, height: width === 1280 ? 720 : 1080 })
    for (const route of ['/devices','/devices/CHG-002','/agent']) {
      await page.goto(url + route)
      await page.waitForLoadState('networkidle')
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    }
  }
  expect(errors).toEqual([])
  records.status = 'PASS'
} catch (error) {
  records.status = 'FAIL'; records.error = String(error)
  await page.screenshot({ path: `${out}/capture-failure.png`, fullPage: true })
  throw error
} finally {
  records.page_errors = errors
  fs.writeFileSync(`${out}/demonstration.json`, JSON.stringify(records,null,2)+'\n')
  await browser.close()
}
