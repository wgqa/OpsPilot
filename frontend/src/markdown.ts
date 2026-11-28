import MarkdownIt from 'markdown-it';

const assistantMarkdown = new MarkdownIt({
  html: false,
  linkify: false,
  breaks: true,
  typographer: false,
});

// Assistant output is untrusted content. Keep raw HTML disabled and images off
// so rendering cannot execute embedded markup or trigger third-party requests.
assistantMarkdown.disable('image');

for (const rule of ['fence', 'code_block'] as const) {
  const render = assistantMarkdown.renderer.rules[rule];
  if (render) {
    assistantMarkdown.renderer.rules[rule] = (...args) => render(...args)
      .replace('<pre>', '<pre tabindex="0" aria-label="代码块">');
  }
}

export function renderAssistantMarkdown(source: string): string {
  return assistantMarkdown.render(source);
}
