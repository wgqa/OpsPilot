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

export function renderAssistantMarkdown(source: string): string {
  return assistantMarkdown.render(source);
}
