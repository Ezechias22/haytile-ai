/** Local title suggestion: no provider request or API spend. */
export function suggestTitle(prompt: string, fallback: string): string {
  const lines = prompt
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/^[#*`\s]+|[*`\s]+$/g, ''))
    .filter(Boolean);
  const explicit = lines
    .map((line) =>
      line.match(/^(?:tit|titre|title|título|titulo|عنوان|标题|judul|kichwa)\s*[:：]\s*(.+)$/iu),
    )
    .find(Boolean);
  const raw = (explicit?.[1] || lines.find((line) => !/^\[.*\]$/.test(line)) || fallback)
    .replace(/^["“«]+|["”»]+$/g, '')
    .trim();
  if (raw.length <= 76) return raw || fallback;
  const short = raw.slice(0, 73);
  return (short.lastIndexOf(' ') > 40 ? short.slice(0, short.lastIndexOf(' ')) : short) + '…';
}
