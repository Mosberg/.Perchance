"use strict";

/**
 * Perchance Parser
 * ----------------
 * A line-oriented parser for .pjs files. Produces a structured AST
 * suitable for completion, diagnostics, definition-lookup, symbols,
 * graphing, formatting, and preview generation.
 *
 * AST node types:
 *   { type: 'import', name, plugin, line }
 *   { type: 'meta', key, subkeys: [{key, line}], line }
 *   { type: 'output', expr, line }
 *   { type: 'table', name, line, items: Item[], endLine }
 *   { type: 'function', name, params: [{name, default}], line, endLine, body: BodyLine[] }
 *   { type: 'assignment', name, value, line }   (scalar or expression)
 *   { type: 'comment', text, line }
 *   { type: 'blank', line }
 * Item:
 *   { indent, text, weight: null | {type:'static', value:number} | {type:'dynamic', expr:string},
 *     references: string[], jsBlocks: string[], line, raw }
 */

const BUILTINS = [
  "selectOne",
  "selectMany",
  "selectUnique",
  "getLength",
  "joinItems",
  "evaluateItem",
  "selectAll",
];

function parse(text) {
  const lines = text.split(/\r?\n/);
  const nodes = [];
  let i = 0;
  const n = lines.length;

  while (i < n) {
    const raw = lines[i];
    const lineNo = i + 1;
    const trimmed = raw.trim();

    // blank line
    if (trimmed === "") {
      nodes.push({ type: "blank", line: lineNo });
      i++;
      continue;
    }

    // full-line comment
    if (trimmed.startsWith("//")) {
      nodes.push({ type: "comment", text: trimmed, line: lineNo });
      i++;
      continue;
    }
    if (trimmed.startsWith("/*")) {
      // could be single or multi-line; consume until */
      let block = trimmed;
      const startLine = lineNo;
      while (!block.includes("*/") && i + 1 < n) {
        i++;
        block += "\n" + lines[i];
      }
      nodes.push({ type: "comment", text: block, line: startLine });
      i++;
      continue;
    }

    // $output = ...
    if (/^\$output\s*=/.test(trimmed)) {
      nodes.push({
        type: "output",
        expr: trimmed.replace(/^\$output\s*=\s*/, ""),
        line: lineNo,
      });
      i++;
      continue;
    }

    // $meta or $meta.key
    if (/^\$meta(\.\w+)?\s*$/.test(trimmed) || /^\$meta\s*=/.test(trimmed)) {
      // collect indented subkeys
      const metaNode = {
        type: "meta",
        key: "$meta",
        subkeys: [],
        line: lineNo,
        endLine: lineNo,
      };
      i++;
      while (i < n && /^\s+\S/.test(lines[i]) && !/^\s*$/.test(lines[i])) {
        const sub = lines[i].trim();
        const m = sub.match(/^(\w+)\s*=\s*(.*)$/);
        if (m) {
          metaNode.subkeys.push({ key: m[1], value: m[2], line: i + 1 });
        } else {
          metaNode.subkeys.push({ key: sub, value: null, line: i + 1 });
        }
        metaNode.endLine = i + 1;
        i++;
      }
      nodes.push(metaNode);
      continue;
    }

    // import:  name = {import:plugin}
    {
      const m = trimmed.match(
        /^(\w+)\s*=\s*\{\s*import\s*:\s*([\w-]+)\s*\}\s*$/,
      );
      if (m) {
        nodes.push({ type: "import", name: m[1], plugin: m[2], line: lineNo });
        i++;
        continue;
      }
    }

    // function:  name(params) =>
    {
      const m = trimmed.match(/^(\w+)\s*\(([^)]*)\)\s*=>\s*$/);
      if (m) {
        const fName = m[1];
        const params = parseParams(m[2]);
        const funcNode = {
          type: "function",
          name: fName,
          params,
          line: lineNo,
          endLine: lineNo,
          body: [],
        };
        i++;
        // consume indented body until dedent or =>
        while (i < n) {
          const bl = lines[i];
          if (/^\S/.test(bl)) break; // dedent to column 0
          funcNode.body.push({ text: bl.trim(), raw: bl, line: i + 1 });
          funcNode.endLine = i + 1;
          i++;
        }
        nodes.push(funcNode);
        continue;
      }
    }

    // assignment (no indented children): name = value
    {
      const m = trimmed.match(/^(\w+)\s*=\s*(.+)$/);
      if (m) {
        // Check if next line is indented (making this a table header instead)
        const hasNext = i + 1 < n;
        const nextIndented =
          hasNext && /^\s+\S/.test(lines[i + 1]) && !/^\s*$/.test(lines[i + 1]);
        if (!nextIndented) {
          nodes.push({
            type: "assignment",
            name: m[1],
            value: m[2],
            line: lineNo,
          });
          i++;
          continue;
        }
        // If it IS followed by indented content, it's a table whose first
        // item uses '=' — rare. Fall through to table handler.
      }
    }

    // table: bare name at col 0, followed by indented items
    {
      const m = trimmed.match(/^(\w+)$/);
      if (m) {
        const tableName = m[1];
        const tableNode = {
          type: "table",
          name: tableName,
          line: lineNo,
          items: [],
          endLine: lineNo,
        };
        i++;
        while (i < n) {
          const il = lines[i];
          if (/^\s*$/.test(il)) {
            i++;
            continue;
          } // skip blanks within table
          if (/^\S/.test(il)) break; // dedent
          const item = parseItem(il, i + 1);
          tableNode.items.push(item);
          tableNode.endLine = i + 1;
          i++;
        }
        nodes.push(tableNode);
        continue;
      }
    }

    // fallback: treat as a comment / unknown
    nodes.push({ type: "comment", text: trimmed, line: lineNo });
    i++;
  }

  return nodes;
}

function parseParams(s) {
  if (!s.trim()) return [];
  return s.split(",").map((p) => {
    p = p.trim();
    const eq = p.indexOf("=");
    if (eq >= 0) {
      return { name: p.slice(0, eq).trim(), default: p.slice(eq + 1).trim() };
    }
    return { name: p, default: null };
  });
}

function parseItem(line, lineNo) {
  const indent = line.match(/^(\s*)/)[1].length;
  const content = line.trim();
  const raw = line;

  // weight detection:  text^N  or  text^[expr]  or  text^
  let weight = null;
  let text = content;
  const wMatch = content.match(/^(.*?)\^(\d+|\[[^[\]]*\]|)$/);
  if (wMatch && content.includes("^")) {
    // make sure ^ isn't inside a JS block or string
    const caretIdx = findWeightCaret(content);
    if (caretIdx >= 0) {
      text = content.slice(0, caretIdx).trim();
      const wPart = content.slice(caretIdx + 1).trim();
      if (wPart === "") {
        weight = { type: "static", value: 1 };
      } else if (/^\d+$/.test(wPart)) {
        weight = { type: "static", value: parseInt(wPart, 10) };
      } else if (/^\[.*\]$/.test(wPart)) {
        weight = { type: "dynamic", expr: wPart.slice(1, -1) };
      }
    }
  }

  const references = extractReferences(text);
  const jsBlocks = extractJsBlocks(text);

  return { indent, text, weight, references, jsBlocks, line: lineNo, raw };
}

// Find the ^ that acts as a weight marker, not one inside [..] or ".." or '..'
function findWeightCaret(s) {
  let depthBracket = 0;
  let depthBrace = 0;
  let inStr = null;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (inStr) {
      if (c === "\\") {
        i++;
        continue;
      }
      if (c === inStr) inStr = null;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      inStr = c;
      continue;
    }
    if (c === "[") depthBracket++;
    else if (c === "]") depthBracket--;
    else if (c === "{") depthBrace++;
    else if (c === "}") depthBrace--;
    else if (c === "^" && depthBracket === 0 && depthBrace === 0) return i;
  }
  return -1;
}

// Extract table references from [tableName] patterns in JS blocks and bare [name] refs
function extractReferences(text) {
  const refs = [];
  const seen = new Set();

  // [tableName] — bare reference
  const re = /\[([a-zA-Z_]\w*)\]/g;
  let m;
  while ((m = re.exec(text))) {
    const name = m[1];
    if (BUILTINS.includes(name)) continue;
    if (!seen.has(name)) {
      seen.add(name);
      refs.push(name);
    }
  }

  // [tableName.method] and [tableName.selectOne] patterns
  const re2 = /\[([a-zA-Z_]\w*)\./g;
  while ((m = re2.exec(text))) {
    const name = m[1];
    if (BUILTINS.includes(name)) continue;
    if (name === "root" || name === "this") continue;
    if (!seen.has(name)) {
      seen.add(name);
      refs.push(name);
    }
  }

  return refs;
}

function extractJsBlocks(text) {
  const blocks = [];
  let depth = 0;
  let start = -1;
  let inStr = null;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inStr) {
      if (c === "\\") {
        i++;
        continue;
      }
      if (c === inStr) inStr = null;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      inStr = c;
      continue;
    }
    if (c === "[") {
      if (depth === 0) start = i;
      depth++;
    } else if (c === "]") {
      depth--;
      if (depth === 0 && start >= 0) {
        blocks.push(text.slice(start + 1, i));
        start = -1;
      }
    }
  }
  return blocks;
}

// Count bracket balance for diagnostics
function bracketBalance(text) {
  let brackets = 0,
    braces = 0,
    parens = 0;
  let inStr = null;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inStr) {
      if (c === "\\") {
        i++;
        continue;
      }
      if (c === inStr) inStr = null;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      inStr = c;
      continue;
    }
    if (c === "[") brackets++;
    else if (c === "]") brackets--;
    else if (c === "{") braces++;
    else if (c === "}") braces--;
    else if (c === "(") parens++;
    else if (c === ")") parens--;
  }
  return { brackets, braces, parens };
}
