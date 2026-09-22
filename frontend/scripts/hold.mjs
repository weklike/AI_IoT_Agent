import { chromium } from '@playwright/test'
import fs from 'node:fs'
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } })
const observed = new Map(), errors = []
page.on('pageerror', error => errors.push(error.message))
await page.goto(process.env.PERF_BASE_URL + '/devices')
await page.getByTestId('device-card').first().waitFor()
fs.writeFileSync(process.env.PERF_OUTPUT + '/browser-ready', 'ready')
const sample = async () => {
  const ids = await page.locator('[data-message-id]').evaluateAll(elements => elements.map(e => e.dataset.messageId).filter(Boolean))
  for (const id of ids) if (!observed.has(id)) observed.set(id, new Date().toISOString())
}
let closing = false
const shutdown = async () => {
  if (closing) return; closing = true
  clearInterval(timer)
  fs.writeFileSync(process.env.PERF_OUTPUT + '/browser-observed.json', JSON.stringify({ observations: Object.fromEntries(observed), errors }, null, 2))
  await page.screenshot({ path: process.env.PERF_OUTPUT + '/browser-final.png', fullPage: true })
  await browser.close()
  process.exit(0)
}
const timer = setInterval(() => { if (!closing) sample().catch(error => errors.push(error.message)) }, 100)
process.on('SIGTERM', shutdown)
process.on('SIGINT', shutdown)
