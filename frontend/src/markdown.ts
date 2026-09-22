import MarkdownIt from 'markdown-it'

// Model answers are untrusted text. Never enable raw HTML or HTML-producing plugins.
const markdown = new MarkdownIt({ html: false, breaks: true, linkify: false })

markdown.validateLink = url => {
  try {
    return ['http:', 'https:', 'mailto:'].includes(new URL(url, 'https://markdown.invalid').protocol)
  } catch {
    return false
  }
}

markdown.renderer.rules.link_open = (tokens, index, options, _env, renderer) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  return renderer.renderToken(tokens, index, options)
}

// Do not let an answer trigger external image requests; retain its alternative text.
markdown.renderer.rules.image = (tokens, index) => markdown.utils.escapeHtml(tokens[index].content)

for (const rule of ['heading_open', 'heading_close']) {
  markdown.renderer.rules[rule] = (tokens, index, options, _env, renderer) => {
    tokens[index].tag = 'h' + Math.min(6, Number(tokens[index].tag.slice(1)) + 2)
    return renderer.renderToken(tokens, index, options)
  }
}

markdown.renderer.rules.table_open = () => '<div class="markdown-table" role="region" aria-label="回答中的表格，可横向滚动" tabindex="0"><table>\n'
markdown.renderer.rules.table_close = () => '</table></div>\n'

export function renderMarkdown(source: string): string {
  return markdown.render(source)
}
