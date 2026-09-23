import { chromium, expect } from '@playwright/test'
import fs from 'node:fs'

const base = process.env.PERF_BASE_URL
const output = process.env.PERF_OUTPUT
const count = Number(process.env.PERF_SAMPLES || '20')
const results = { controls: [], alarms: [], errors: [] }
const save = () => fs.writeFileSync(output + '/browser-results.json', JSON.stringify(results, null, 2))
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } })
page.on('pageerror', error => { results.errors.push(error.message); save() })
async function get(path) {
  const response = await page.request.get(base + path)
  if (!response.ok()) throw new Error(`HTTP ${response.status()} on ${path}`)
  return (await response.json()).data
}
try {
  await page.goto(base + '/devices/CHG-001')
  await expect(page.getByRole('button', { name: '开始充电', exact: true })).toBeEnabled({ timeout: 15000 })
  for (let index = 0; index < count; index++) {
    const start = index % 2 === 0
    const record = { index, action: start ? 'start' : 'stop', status: 'NOT_RUN' }
    results.controls.push(record); save()
    try {
      const acceptedResponse = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/charging/' + record.action))
      await page.getByRole('button', { name: start ? '开始充电' : '停止充电', exact: true }).click()
      const response = await acceptedResponse
      record.http_status = response.status()
      record.accepted = (await response.json()).data
      if (response.status() !== 202) throw new Error('Control was not accepted')
      await expect(page.getByTestId('charging-command')).toContainText('效果已验证', { timeout: 11000 })
      await expect(page.getByTestId('charging-runtime').locator('.section-title .pill')).toHaveText(start ? 'ACTIVE' : 'IDLE', { timeout: 6000 })
      await expect(page.locator('.detail-metrics').getByText('数据新鲜', { exact: true })).toBeVisible()
      record.seen_at = new Date().toISOString()
      record.visible_text = await page.getByTestId('charging-runtime').innerText()
      record.command = await get('/api/device-commands/' + record.accepted.command_id)
      record.state = await get('/api/devices/CHG-001')
      record.latency_ms = Date.parse(record.seen_at) - Date.parse(record.command.ack_at)
      record.correct = record.command.status === 'applied' && record.command.verification_status === 'verified'
        && record.state.data_fresh && record.state.session_state === (start ? 'ACTIVE' : 'IDLE')
        && record.state.applied_control_generation >= record.command.generation
        && (!start || record.state.session_id === record.accepted.session_id)
      record.status = record.correct && record.latency_ms >= 0 && record.latency_ms <= 4000 ? 'PASS' : 'FAIL'
      save()
    } catch (error) { record.status = 'FAIL'; record.error = error.message; save(); throw error }
  }
  const alarms = page.getByTestId('alarm-list')
  for (let index = 0; index < count; index++) {
    const record = { index, status: 'NOT_RUN' }
    results.alarms.push(record); save()
    try {
      await expect(alarms.locator('.alarm-row')).toHaveCount(0, { timeout: 18000 })
      await page.getByRole('button', { name: '模拟过温', exact: true }).click()
      await expect(alarms.locator('.alarm-row')).toHaveCount(1, { timeout: 10000 })
      await expect(alarms.locator('.alarm-row')).toContainText('CHG-001 · OVERHEAT')
      await expect(alarms.locator('.alarm-row')).toContainText('ACTIVE')
      record.seen_at = new Date().toISOString()
      record.visible_text = await alarms.locator('.alarm-row').innerText()
      const rows = await get('/api/alarms?device_id=CHG-001&condition=ACTIVE')
      record.alarm = rows.items[0]
      const query = new URLSearchParams({ from: new Date(Date.now() - 30000).toISOString(), to: new Date().toISOString() })
      const timeline = await get('/api/devices/CHG-001/timeline?' + query)
      record.created_event = timeline.items.find(item => item.source_type === 'alarm_event'
        && item.detail.alarm_id === record.alarm.alarm_id && item.detail.event_type === 'CREATED')
      if (!record.created_event?.detail?.evidence?.message_id) throw new Error('Missing original triggering sample')
      record.status = 'PENDING_COMMIT_LOG'
      save()
      await page.getByRole('button', { name: '恢复正常', exact: true }).click()
      await expect(alarms.locator('.alarm-row')).toHaveCount(0, { timeout: 18000 })
    } catch (error) { record.status = 'FAIL'; record.error = error.message; save(); throw error }
  }
  await page.screenshot({ path: output + '/browser-final.png', fullPage: true })
} catch (error) {
  results.errors.push(error.message)
  await page.screenshot({ path: output + '/browser-failure.png', fullPage: true }).catch(() => {})
  process.exitCode = 1
} finally {
  save()
  await browser.close()
}
