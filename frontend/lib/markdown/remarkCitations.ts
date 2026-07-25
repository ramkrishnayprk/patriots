// Turns bare "[1]", "[2]" citation markers in prose into link nodes pointing
// at "#cite-1", "#cite-2" — a safe fragment URL that passes react-markdown's
// default URL sanitizer untouched. The actual source lookup (mapping the
// number to a ChatSource, deciding resolved vs. unresolved) happens later,
// in the `a` component override — this plugin only does the syntactic part.
//
// Deliberately hand-rolled instead of using unist-util-visit: the whole
// walk is ~20 lines and doesn't justify a dependency.

interface MdNode {
  type: string;
  value?: string;
  children?: MdNode[];
  [key: string]: unknown;
}

const CITATION_RE = /\[(\d{1,2})\]/g;

function splitTextNode(node: MdNode): MdNode[] {
  const value = node.value ?? "";
  CITATION_RE.lastIndex = 0;
  if (!CITATION_RE.test(value)) return [node];
  CITATION_RE.lastIndex = 0;

  const result: MdNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = CITATION_RE.exec(value)) !== null) {
    if (match.index > lastIndex) {
      result.push({ type: "text", value: value.slice(lastIndex, match.index) });
    }
    const n = match[1];
    result.push({
      type: "link",
      url: `#cite-${n}`,
      children: [{ type: "text", value: n }],
    });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < value.length) {
    result.push({ type: "text", value: value.slice(lastIndex) });
  }
  return result;
}

function walk(node: MdNode): void {
  // Don't citation-ify text inside a link's own label.
  if (node.type === "link") return;
  if (!node.children) return;

  const next: MdNode[] = [];
  for (const child of node.children) {
    if (child.type === "text") {
      next.push(...splitTextNode(child));
    } else {
      walk(child);
      next.push(child);
    }
  }
  node.children = next;
}

export default function remarkCitations() {
  return (tree: MdNode) => {
    walk(tree);
  };
}
