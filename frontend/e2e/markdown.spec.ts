import { test, expect, type Page } from '@playwright/test'
import type { Run } from '../src/types'

// These are presentation fixtures, not real model/API acceptance evidence.
async function showAnswer(page: Page, answer: string, status = 'completed') {
  const run: Run = {
    run_id: 'markdown-presentation-run', request_id: 'markdown-presentation-request',
    question: '查看设备分析', status, answer,
    error_code: status === 'timed_out' ? 'MODEL_TIMEOUT' : null,
    tool_calls: [], llm_mode: 'fixture',
  }
  await page.route('**/api/health', route => route.fulfill({ json: { data: { llm_mode: 'fixture' } } }))
  await page.route('**/api/work-orders', route => route.fulfill({ json: { data: [] } }))
  await page.route('**/api/agent/runs/*', route => route.fulfill({ json: { data: run } }))
  await page.addInitScript(saved => localStorage.setItem('charge-ops-submission-v1', JSON.stringify({
    body: { request_id: saved.request_id, question: saved.question, allow_work_order: false },
    run_id: saved.run_id,
  })), run)
  await page.goto('/agent')
  await expect(page.getByTestId('run-status')).toHaveText(status === 'timed_out' ? '执行超时' : '已完成')
}

const analysis = `# 温度分析

设备 **CHG-002** 当前为 *过温*，请核对采样时间。

## 排查步骤

1. 查看最新样本
2. 检查通风
   - 检查进风口
   - 清理遮挡物

> 这是演示规则告警，不能直接判定硬件损坏。

| 指标 | 数值 |
| --- | ---: |
| 最高温度 | 72 °C |
| 平均温度 | 65.2 °C |

来源：[排查说明](https://example.com/guide)。内部编号 \`CHG-002\`。

\`\`\`json
{"device_id":"CHG-002","note":"<检查>"}
\`\`\`
`

test('Markdown 回答渲染标题、强调、嵌套列表、引用、表格和代码', async ({ page }, info) => {
  await showAnswer(page, analysis)
  const answer = page.locator('.answer')
  await expect(answer.getByRole('heading', { name: '温度分析', level: 3 })).toBeVisible()
  await expect(answer.locator('strong')).toHaveText('CHG-002')
  await expect(answer.locator('em')).toHaveText('过温')
  await expect(answer.locator('ol > li')).toHaveCount(2)
  await expect(answer.locator('ol ul > li')).toHaveCount(2)
  await expect(answer.locator('blockquote')).toContainText('演示规则告警')
  await expect(answer.getByRole('columnheader', { name: '指标' })).toBeVisible()
  await expect(answer.getByRole('cell', { name: '72 °C' })).toBeVisible()
  await expect(answer.locator('pre code')).toHaveText('{"device_id":"CHG-002","note":"<检查>"}\n')
  const link = answer.getByRole('link', { name: '排查说明' })
  await expect(link).toHaveAttribute('href', 'https://example.com/guide')
  await expect(link).toHaveAttribute('rel', /noopener/)
  await expect(answer).not.toContainText('**CHG-002**')
  await page.screenshot({ path: info.outputPath('markdown-answer.png'), fullPage: true })
})

test('模型 Markdown 不执行 HTML、危险链接或自动加载外部图片', async ({ page }) => {
  let externalRequests = 0
  page.on('request', request => { if (request.url().includes('markdown-attack.invalid')) externalRequests++ })
  await showAnswer(page, `**保留正常加粗**

<script>window.__markdownAttack = true</script>
<img src="https://markdown-attack.invalid/html.png" onerror="window.__markdownAttack = true">
<svg onload="window.__markdownAttack = true"></svg>
<iframe src="https://markdown-attack.invalid/frame"></iframe>
<style>body { display: none }</style>

[危险脚本](javascript:alert(1))
[编码脚本](jav&#x61;script:alert(1))
[数据链接](data:text/html,evil)
[本地文件](file:///etc/passwd)
![示意图](https://markdown-attack.invalid/image.png)

\`\`\`html
<img src=x onerror="alert(1)">
\`\`\`
`)
  const answer = page.locator('.answer')
  await expect(answer.locator('strong')).toHaveText('保留正常加粗')
  await expect(answer.locator('script, img, svg, iframe, style')).toHaveCount(0)
  await expect(answer.locator('a')).toHaveCount(0)
  await expect(answer.locator('pre code')).toContainText('<img src=x onerror="alert(1)">')
  expect(await page.evaluate(() => Reflect.get(window, '__markdownAttack'))).toBeUndefined()
  expect(externalRequests).toBe(0)
})

for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
  test(`长表格和代码在 ${size.width}×${size.height} 保持页面无横向溢出`, async ({ page }, info) => {
    await page.setViewportSize(size)
    const columns = Array.from({ length: 16 }, (_, index) => `采样指标${index + 1}`)
    const table = `| ${columns.join(' | ')} |\n| ${columns.map(() => '---').join(' | ')} |\n| ${columns.map(() => 'CHG-002:72.00°C').join(' | ')} |`
    await showAnswer(page, `${analysis}\n${table}\n\n\`\`\`text\n${'CHG-002 '.repeat(150)}\n\`\`\``)
    const answer = page.locator('.answer')
    await expect(answer.getByRole('table')).toHaveCount(2)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    expect(await answer.locator('pre').last().evaluate(element => element.scrollWidth > element.clientWidth)).toBe(true)
    expect(await answer.locator('.markdown-table').last().evaluate(element => element.scrollWidth > element.clientWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath(`markdown-${size.width}.png`), fullPage: true })
  })
}

test('普通错误文本保持可读且不改变任务失败状态', async ({ page }) => {
  await showAnswer(page, '模型请求超时\n请稍后重新发起任务。', 'timed_out')
  await expect(page.getByTestId('run-status')).toHaveText('执行超时')
  await expect(page.locator('.answer')).toContainText('模型请求超时')
  await expect(page.locator('.answer')).toContainText('请稍后重新发起任务。')
  await expect(page.getByRole('button', { name: '开始新任务' })).toBeVisible()
})
