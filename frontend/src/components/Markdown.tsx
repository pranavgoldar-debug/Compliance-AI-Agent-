// Minimal, dependency-free markdown renderer for the in-app Playbook.
// Supports headings (#/##/###), paragraphs, **bold**, `code`, [links](url),
// ordered + unordered lists, GFM tables, > blockquotes, and --- rules.
// Renders React elements (never dangerouslySetInnerHTML) so admin-edited
// content can't inject HTML/scripts. Styled to match the app.
import React from "react";

function renderInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const re = /(\*\*([^*]+)\*\*)|(`([^`]+)`)|(\[([^\]]+)\]\(([^)]+)\))/g;
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[1]) {
      nodes.push(<strong key={key++} className="font-medium text-foreground">{m[2]}</strong>);
    } else if (m[3]) {
      nodes.push(
        <code key={key++} className="font-mono text-[12px] text-aspora-800 bg-aspora-50 rounded px-1.5 py-0.5">
          {m[4]}
        </code>,
      );
    } else if (m[5]) {
      nodes.push(
        <a key={key++} href={m[7]} target="_blank" rel="noreferrer" className="text-aspora-700 hover:underline">
          {m[6]}
        </a>,
      );
    }
    last = re.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function splitRow(line: string): string[] {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
}

function isBlockStart(l: string): boolean {
  const t = l.trim();
  return (
    /^#{1,3}\s/.test(t) ||
    /^[-*]\s+/.test(t) ||
    /^\d+\.\s+/.test(t) ||
    t.startsWith(">") ||
    /^---+$/.test(t) ||
    t === ""
  );
}

export function Markdown({ source }: { source: string }) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) {
      i++;
      continue;
    }

    if (/^---+$/.test(line.trim())) {
      blocks.push(<hr key={key++} className="border-border" />);
      i++;
      continue;
    }

    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      const cls =
        level === 1
          ? "text-lg font-semibold leading-tight"
          : level === 2
            ? "text-base font-semibold mt-2"
            : "text-sm font-semibold mt-1";
      const content = renderInline(h[2]);
      blocks.push(
        level === 1 ? (
          <h1 key={key++} className={cls}>{content}</h1>
        ) : level === 2 ? (
          <h2 key={key++} className={cls}>{content}</h2>
        ) : (
          <h3 key={key++} className={cls}>{content}</h3>
        ),
      );
      i++;
      continue;
    }

    // GFM table: a row with "|" followed by a separator row (| --- | --- |).
    if (
      line.includes("|") &&
      i + 1 < lines.length &&
      lines[i + 1].includes("-") &&
      /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1])
    ) {
      const header = splitRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        rows.push(splitRow(lines[i]));
        i++;
      }
      blocks.push(
        <div key={key++} className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                {header.map((c, ci) => (
                  <th key={ci} className="px-3 py-2 text-left font-medium">{renderInline(c)}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((r, ri) => (
                <tr key={ri} className="align-top">
                  {r.map((c, ci) => (
                    <td key={ci} className="px-3 py-2.5 text-muted-foreground">{renderInline(c)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (line.trim().startsWith(">")) {
      const buf: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        buf.push(lines[i].replace(/^\s*>\s?/, ""));
        i++;
      }
      blocks.push(
        <blockquote
          key={key++}
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900"
        >
          {renderInline(buf.join(" "))}
        </blockquote>,
      );
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      blocks.push(
        <ul key={key++} className="list-disc pl-5 space-y-1 text-sm text-muted-foreground">
          {items.map((it, ix) => (
            <li key={ix}>{renderInline(it)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
        i++;
      }
      blocks.push(
        <ol key={key++} className="list-decimal pl-5 space-y-1 text-sm text-muted-foreground">
          {items.map((it, ix) => (
            <li key={ix}>{renderInline(it)}</li>
          ))}
        </ol>,
      );
      continue;
    }

    // Paragraph — gather consecutive non-block lines.
    const buf: string[] = [line];
    i++;
    while (i < lines.length && !isBlockStart(lines[i])) {
      buf.push(lines[i]);
      i++;
    }
    blocks.push(
      <p key={key++} className="text-sm text-muted-foreground">{renderInline(buf.join(" "))}</p>,
    );
  }

  return <div className="space-y-3">{blocks}</div>;
}
