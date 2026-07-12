"use client";

import { Fragment, type ReactNode } from "react";

/**
 * Lightweight, dependency-free Markdown renderer for AI output (briefs, reports).
 * Supports headings, bold/italic/code, links, blockquotes, ordered/unordered
 * lists, fenced code blocks, tables and horizontal rules. Kept intentionally
 * small and offline (no external markdown library).
 */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return <div className={className}>{renderBlocks(children ?? "")}</div>;
}

// ---- Inline (bold / italic / code / links) --------------------------------

function inline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\))/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = pattern.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const key = `${keyBase}-${i++}`;
    if (m[2]) nodes.push(<strong key={key}>{m[2]}</strong>);
    else if (m[3]) nodes.push(<em key={key}>{m[3]}</em>);
    else if (m[4]) nodes.push(<code key={key} className="rounded bg-slate-100 px-1 py-0.5 text-[0.85em] text-foreground">{m[4]}</code>);
    else if (m[5] && m[6]) {
      const safe = /^(https?:|\/)/.test(m[6]) ? m[6] : "#";
      nodes.push(<a key={key} href={safe} target="_blank" rel="noopener noreferrer" className="text-brand-600 hover:underline">{m[5]}</a>);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

// ---- Blocks ----------------------------------------------------------------

function renderBlocks(md: string): ReactNode[] {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  let k = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block.
    if (line.trim().startsWith("```")) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) { body.push(lines[i]); i++; }
      i++; // closing fence
      out.push(
        <pre key={`c${k++}`} className="my-2 overflow-x-auto rounded-lg bg-[#0f172a] p-3 text-xs text-[#e5e9f0]">
          <code>{body.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    // Table (header row + separator row of dashes).
    if (line.includes("|") && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes("-")) {
      const parseRow = (r: string) => r.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((c) => c.trim());
      const headers = parseRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") { rows.push(parseRow(lines[i])); i++; }
      out.push(
        <div key={`t${k++}`} className="my-3 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>{headers.map((h, ci) => (
                <th key={ci} className="border border-border bg-slate-50 px-3 py-1.5 text-left font-semibold text-foreground">{inline(h, `th${ci}`)}</th>
              ))}</tr>
            </thead>
            <tbody>{rows.map((row, ri) => (
              <tr key={ri}>{row.map((c, ci) => (
                <td key={ci} className="border border-border px-3 py-1.5 text-muted">{inline(c, `td${ri}-${ci}`)}</td>
              ))}</tr>
            ))}</tbody>
          </table>
        </div>,
      );
      continue;
    }

    // Headings.
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      const sizes = ["text-xl", "text-lg", "text-base", "text-sm"];
      out.push(
        <p key={`h${k++}`} className={`mt-4 mb-1 font-bold text-foreground ${sizes[level - 1]}`}>{inline(h[2], `h${k}`)}</p>,
      );
      i++;
      continue;
    }

    // Horizontal rule.
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      out.push(<hr key={`hr${k++}`} className="my-3 border-border" />);
      i++;
      continue;
    }

    // Blockquote.
    if (line.trim().startsWith(">")) {
      const body: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) { body.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
      out.push(
        <blockquote key={`q${k++}`} className="my-2 border-l-4 border-brand-300 bg-brand-50/40 px-3 py-1.5 text-sm text-muted">
          {inline(body.join(" "), `q${k}`)}
        </blockquote>,
      );
      continue;
    }

    // Unordered list.
    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*+]\s+/, "")); i++; }
      out.push(
        <ul key={`u${k++}`} className="my-2 list-disc space-y-0.5 pl-5 text-sm text-foreground">
          {items.map((it, ii) => <li key={ii}>{inline(it, `u${k}-${ii}`)}</li>)}
        </ul>,
      );
      continue;
    }

    // Ordered list.
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+\.\s+/, "")); i++; }
      out.push(
        <ol key={`o${k++}`} className="my-2 list-decimal space-y-0.5 pl-5 text-sm text-foreground">
          {items.map((it, ii) => <li key={ii}>{inline(it, `o${k}-${ii}`)}</li>)}
        </ol>,
      );
      continue;
    }

    // Blank line.
    if (line.trim() === "") { i++; continue; }

    // Paragraph (gather consecutive non-structural lines).
    const para: string[] = [line];
    i++;
    while (i < lines.length && lines[i].trim() !== "" && !/^(#{1,4}\s|\s*[-*+]\s|\s*\d+\.\s|>|```)/.test(lines[i]) && !lines[i].includes("|")) {
      para.push(lines[i]); i++;
    }
    out.push(<p key={`p${k++}`} className="my-1.5 text-sm text-foreground">{inline(para.join(" "), `p${k}`)}</p>);
  }

  return out.map((n, idx) => <Fragment key={idx}>{n}</Fragment>);
}
