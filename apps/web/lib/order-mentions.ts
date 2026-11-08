import type { Link, Parent, Root, RootContent, Text } from "mdast";

function erpOrderPath(id: string) {
  return `/orders/${id}?open=erpnext`;
}

type OrderLink = Link & { children: [Text] };

export function orderMentions(text: string): (Text | OrderLink)[] {
  const tokens: (Text | OrderLink)[] = [];
  const pattern = /\b(?:wwi:sales_order:|(?:(purchase|work|production|supplier)[\s-]+)?(?:sales[\s-]+)?order(?:\s+(?:number|no\.?|id))?\s*[:#]?\s*)([1-9][0-9]{0,9})(?![\w-]|\.[0-9])/gi;
  let start = 0;
  for (const match of text.matchAll(pattern)) {
    const [, otherKind, id] = match;
    if (otherKind || Number(id) > 2147483647) continue;
    const end = match.index + match[0].length;
    const prefix = text.slice(start, end - id.length);
    if (prefix) tokens.push({ type: "text", value: prefix });
    tokens.push({ type: "link", url: erpOrderPath(id), children: [{ type: "text", value: id }] });
    start = end;
  }
  if (start < text.length) tokens.push({ type: "text", value: text.slice(start) });
  return tokens;
}

export function remarkOrderMentions() {
  function replaceText(parent: Parent) {
    parent.children = parent.children.flatMap<RootContent>((child) => {
      if (child.type === "text") return orderMentions(child.value);
      if ("children" in child && child.type !== "link" && child.type !== "linkReference") replaceText(child);
      return [child];
    });
  }
  return (tree: Root) => replaceText(tree);
}
