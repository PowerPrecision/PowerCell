/**
 * Conversão mínima Markdown → HTML para cartões (changelog, análise IA).
 * O HTML resultante deve passar sempre por `sanitizeHtml` antes de renderizar.
 */
export function markdownToHtml(md) {
  if (!md || typeof md !== "string") return "";
  let html = md
    .replace(/^### (.+)$/gm, '<h3 class="text-sm font-semibold mt-3 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-base font-bold mt-4 mb-2">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-lg font-bold mt-4 mb-2">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>")
    .replace(/^[-*] (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/\n\n/g, '</p><p class="mb-2">')
    .replace(/\n/g, "<br/>");
  html = `<p class="mb-2">${html}</p>`;
  return html.replace(/<p class="mb-2"><\/p>/g, "");
}
