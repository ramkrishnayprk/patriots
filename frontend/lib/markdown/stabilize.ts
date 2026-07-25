// Makes an in-progress streamed markdown string safe to render mid-stream.
// Applied ONLY while a message is still streaming (finalized content renders
// raw, untouched). This never parses or builds a tree — it only inspects the
// tail of the string and closes or truncates dangling syntax, so a failure
// here is cosmetic and lasts a single ~40ms frame, never wrong or unsafe
// output. See the plan doc for why this is fine to hand-roll while the
// actual markdown parser (react-markdown) is not.

function fenceGuard(text: string): string {
  const fenceCount = (text.match(/^\s*```/gm) ?? []).length;
  return fenceCount % 2 === 1 ? `${text}\n\`\`\`` : text;
}

const TABLE_ROW_RE = /^\s*\|/;
const TABLE_DELIMITER_RE = /^\s*\|?[\s:|-]+\|?\s*$/;

function tableGuard(text: string): string {
  const lines = text.split("\n");
  let start = lines.length;
  while (start > 0 && TABLE_ROW_RE.test(lines[start - 1])) start--;
  const run = lines.slice(start);

  if (run.length === 0) return text;
  if (run.length < 2) return lines.slice(0, start).join("\n");
  if (!TABLE_DELIMITER_RE.test(run[1])) return lines.slice(0, start).join("\n");

  // Header + delimiter are both present and well-formed. If there's at
  // least one data row and the last one looks incomplete, drop just that row.
  const last = run[run.length - 1];
  if (run.length > 2 && !/\|\s*$/.test(last.trimEnd())) {
    return lines.slice(0, lines.length - 1).join("\n");
  }
  return text;
}

function headingGuard(text: string): string {
  return text.replace(/\n\s*#{1,6}\s*$/, "").replace(/^\s*#{1,6}\s*$/, "");
}

function nascentBulletGuard(text: string): string {
  return text.replace(/\n\s*[-*+]\s*$/, "").replace(/^\s*[-*+]\s*$/, "");
}

function linkGuard(text: string): string {
  const lastOpen = text.lastIndexOf("[");
  const lastClose = text.lastIndexOf("]");
  if (lastOpen > lastClose) return text.slice(0, lastOpen);

  const dangling = text.match(/\[[^[\]]*\]\([^()]*$/);
  if (dangling && dangling.index !== undefined) {
    return text.slice(0, dangling.index);
  }
  return text;
}

function inlineCodeGuard(text: string): string {
  const withoutFences = text.replace(/```[\s\S]*?```/g, "");
  const backtickCount = (withoutFences.match(/`/g) ?? []).length;
  return backtickCount % 2 === 1 ? `${text}\`` : text;
}

function emphasisGuard(text: string): string {
  let result = text;

  const strongStars = (result.match(/\*\*/g) ?? []).length;
  if (strongStars % 2 === 1) result += "**";

  const strongUnders = (result.match(/__/g) ?? []).length;
  if (strongUnders % 2 === 1) result += "__";

  // Single "*"/"_" not part of a "**"/"__" pair and not a leading bullet marker.
  const singleStars = (result.replace(/\*\*/g, "").match(/\*/g) ?? []).length;
  if (singleStars % 2 === 1) result += "*";

  const singleUnders = (result.replace(/__/g, "").match(/(?<![a-zA-Z0-9])_|_(?![a-zA-Z0-9])/g) ?? []).length;
  if (singleUnders % 2 === 1) result += "_";

  return result;
}

const GUARDS = [
  fenceGuard,
  tableGuard,
  headingGuard,
  nascentBulletGuard,
  linkGuard,
  inlineCodeGuard,
  emphasisGuard,
];

export function stabilizeStreamingMarkdown(text: string): string {
  return GUARDS.reduce((acc, guard) => guard(acc), text);
}

export function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

// The citation number a source answers to. The backend drops uncited sources
// but keeps each survivor's original ordinal (see resolve_sources in
// backend/app/generation/pipeline.py), so an answer citing [1] and [3] yields a
// two-item array carrying ordinals 1 and 3. Indexing by array position would
// renumber [3] to 2 in the footer and leave the inline [3] unresolved, so the
// ordinal must come from the source itself. Non-numeric ids (chunk ids from
// other retrieval paths) fall back to position.
export function sourceOrdinal(source: { id?: string }, index: number): number {
  const parsed = Number(source?.id);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : index + 1;
}
