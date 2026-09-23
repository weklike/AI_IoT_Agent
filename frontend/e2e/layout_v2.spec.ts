import { test, expect } from '@playwright/test'

for (const width of [1280, 1920]) {
  test(`@v2 three-page layout ${width}`, async ({ page }, info) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await page.setViewportSize({ width, height: width === 1280 ? 720 : 1080 })
    for (const [path, heading] of [['/devices', '设备总览'], ['/devices/CHG-001', 'CHG-001'], ['/agent', 'Agent 助手']]) {
      await page.goto(path)
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
      await page.waitForLoadState('networkidle')
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.screenshot({ path: info.outputPath(`${heading}-${width}.png`), fullPage: true })
    }
    expect(errors).toEqual([])
  })
}

test('@v2 overview guide anchor scrolls on direct load and on click', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 })
  // Control: without a fragment the power panel starts below the fold.
  await page.goto('/devices')
  await expect(page.getByTestId('device-card')).toHaveCount(3)
  await expect(page.locator('#station-power')).not.toBeInViewport()
  // Opening a shared link is a full document load, not a same-page fragment change.
  await page.goto('about:blank')
  await page.goto('/devices#station-power')
  await expect(page.getByTestId('device-card')).toHaveCount(3)
  await expect(page.locator('#station-power')).toBeInViewport()
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.getByRole('link', { name: /告警与巡检/ }).click()
  await expect(page.locator('#station-patrol')).toBeInViewport()
})
