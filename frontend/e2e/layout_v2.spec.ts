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
