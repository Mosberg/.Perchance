"use strict";

const vscode = require("vscode");
const {
  parse,
  BUILTINS,
  bracketBalance,
  extractReferences,
} = require("./parser");

// ── Built-in docs ────────────────────────────────────────────────
const BUILTIN_DOCS = {
  selectOne: {
    sig: "table.selectOne",
    doc: "Select one random item from this table. Returns a node object; use `.evaluateItem` to get the string.",
    params: [],
  },
  selectMany: {
    sig: "table.selectMany(count)",
    doc: "Select `count` items from the table (with repeats). Returns an array of node objects.",
    params: [
      {
        name: "count",
        doc: "Number of items to select (with repeats allowed).",
      },
    ],
  },
  selectUnique: {
    sig: "table.selectUnique(count)",
    doc: "Select `count` unique items from the table (no repeats).",
    params: [{ name: "count", doc: "Number of unique items to select." }],
  },
  getLength: {
    sig: "table.getLength",
    doc: "Returns the number of items in this table.",
    params: [],
  },
  joinItems: {
    sig: "table.joinItems(separator)",
    doc: "Joins all items in the table with the given separator and returns the combined string.",
    params: [{ name: "separator", doc: "String inserted between items." }],
  },
  evaluateItem: {
    sig: "node.evaluateItem",
    doc: "Evaluates a captured selection and returns its string value.",
    params: [],
  },
  selectAll: {
    sig: "table.selectAll",
    doc: "Returns an array of all node objects in the table. Use for iteration in JS.",
    params: [],
  },
};

const KEYWORD_DOCS = {
  root: "`root` gives access to all top-level names (tables, variables, functions, imports) from anywhere in the file.",
  this: "`this` refers to the enclosing list/node object during evaluation.",
  $meta:
    "Generator metadata block: title, description, image, tags, and header options.",
  $output:
    "Top-level output — when this generator is imported, this is what the importer receives instead of the whole root.",
};

function getSymbolsFromDoc(text) {
  const nodes = parse(text);
  const symbols = [];
  for (const node of nodes) {
    if (
      node.type === "table" ||
      node.type === "function" ||
      node.type === "assignment" ||
      node.type === "import"
    ) {
      symbols.push({ name: node.name, kind: node.type, node });
    }
  }
  return symbols;
}

// ── Completion Provider ──────────────────────────────────────────
class CompletionProvider {
  constructor(index) {
    this.index = index;
  }

  provideCompletionItems(doc, pos, token, ctx) {
    const line = doc.lineAt(pos).text;
    const prefix = line.slice(0, pos.character);
    const cfg = vscode.workspace.getConfiguration("perchance");
    const items = [];

    // Detect context: are we after a '.'?
    const dotMatch = prefix.match(/(\w+)\.(\w*)$/);
    if (dotMatch) {
      const tableName = dotMatch[1];
      return this.completeTableMethods(tableName, doc, pos);
    }

    // Inside a JS block?
    const inJs = isInJsBlock(line, pos.character);
    if (inJs) {
      // offer table names + builtins
      const allNames = this.getAllNames(doc);
      for (const name of allNames) {
        items.push(
          new vscode.CompletionItem(name, vscode.CompletionItemKind.Variable),
        );
      }
      if (cfg.get("completion.builtinFunctions", true)) {
        for (const b of BUILTINS) {
          const it = new vscode.CompletionItem(
            b,
            vscode.CompletionItemKind.Method,
          );
          it.detail = BUILTIN_DOCS[b] ? BUILTIN_DOCS[b].sig : b;
          it.documentation = BUILTIN_DOCS[b] ? BUILTIN_DOCS[b].doc : "";
          items.push(it);
        }
        for (const kw of [
          "root",
          "this",
          "Math",
          "JSON",
          "String",
          "Array",
          "Object",
          "Number",
          "Boolean",
        ]) {
          items.push(
            new vscode.CompletionItem(kw, vscode.CompletionItemKind.Keyword),
          );
        }
      }
      return items;
    }

    // In normal text — offer table references
    const refMatch = prefix.match(/\[([a-zA-Z_]\w*)$/);
    if (refMatch) {
      const allNames = this.getAllNames(doc);
      for (const name of allNames) {
        const it = new vscode.CompletionItem(
          name,
          vscode.CompletionItemKind.Reference,
        );
        items.push(it);
      }
      return items;
    }

    // Inline alternation context — offer table names inside { }
    const braceMatch = prefix.match(/\{([^{}|]*)$/);
    if (braceMatch) {
      const allNames = this.getAllNames(doc);
      for (const name of allNames) {
        items.push(
          new vscode.CompletionItem(name, vscode.CompletionItemKind.Reference),
        );
      }
      return items;
    }

    // Top-level: nothing special beyond snippets (handled by package.json)
    return [];
  }

  completeTableMethods(tableName, doc, pos) {
    const items = [];
    for (const m of [
      "selectOne",
      "selectMany",
      "selectUnique",
      "getLength",
      "joinItems",
      "selectAll",
      "evaluateItem",
    ]) {
      const it = new vscode.CompletionItem(m, vscode.CompletionItemKind.Method);
      if (BUILTIN_DOCS[m]) {
        it.detail = `${tableName}.${BUILTIN_DOCS[m].sig}`;
        it.documentation = BUILTIN_DOCS[m].doc;
        // build signature for selectMany/selectUnique
        if (m === "selectMany" || m === "selectUnique") {
          it.insertText = new vscode.SnippetString(`${m}(\${1:count})`);
        }
      }
      items.push(it);
    }
    return items;
  }

  getAllNames(doc) {
    const names = new Set();
    // from current doc
    const text = doc.getText();
    for (const s of getSymbolsFromDoc(text)) names.add(s.name);
    // from index
    for (const name of this.index.getAllDefinedNames()) names.add(name);
    return [...names];
  }
}

// ── Hover Provider ───────────────────────────────────────────────
class HoverProvider {
  constructor(index) {
    this.index = index;
  }

  provideHover(doc, pos, token) {
    const cfg = vscode.workspace.getConfiguration("perchance");
    if (!cfg.get("hover.enabled", true)) return null;

    const range = doc.getWordRangeAtPosition(pos, /[a-zA-Z_$]\w*/);
    if (!range) return null;
    const word = doc.getText(range);
    const line = doc.lineAt(pos).text;

    // Builtin methods
    if (BUILTIN_DOCS[word]) {
      const d = BUILTIN_DOCS[word];
      const md = new vscode.MarkdownString();
      md.appendMarkdown(`**\`${d.sig}\`**\n\n${d.doc}`);
      if (d.params.length) {
        md.appendMarkdown("\n\n**Parameters:**\n");
        for (const p of d.params)
          md.appendMarkdown(`- \`${p.name}\` — ${p.doc}\n`);
      }
      return new vscode.Hover(md, range);
    }

    // Keywords
    if (KEYWORD_DOCS[word]) {
      const md = new vscode.MarkdownString();
      md.appendMarkdown(KEYWORD_DOCS[word]);
      return new vscode.Hover(md, range);
    }

    // Table / variable / function definitions
    const defs =
      this.index.getDefinition(word) ||
      getSymbolsFromDoc(doc.getText()).filter((s) => s.name === word);
    if (!defs.length) return null;
    const def = defs[0];
    const md = new vscode.MarkdownString();
    const kindLabel = {
      table: "Table",
      function: "Function",
      variable: "Variable",
      import: "Import",
      meta: "Meta",
      output: "Output",
    };
    md.appendMarkdown(
      `**${kindLabel[def.kind] || def.kind}: \`${def.name}\`**\n\n`,
    );
    md.appendMarkdown(
      `Defined at ${shortPath(def.uri || doc.uri)}:${def.line}\n`,
    );

    if (def.kind === "table" && cfg.get("hover.showItems", true)) {
      const tableNode = def.node;
      const itemCount = tableNode.items.length;
      md.appendMarkdown(`\n**${itemCount} items:**\n`);
      const preview = tableNode.items.slice(0, 8).map((it) => {
        let line = `  \`${it.text}\``;
        if (it.weight) {
          line +=
            it.weight.type === "static"
              ? ` ^${it.weight.value}`
              : ` ^[${it.weight.expr}]`;
        }
        return line;
      });
      md.appendMarkdown(preview.join("\n"));
      if (itemCount > 8) md.appendMarkdown(`\n\n*…and ${itemCount - 8} more*`);
    }

    if (def.kind === "function") {
      const params = def.node.params
        .map((p) => (p.default ? `${p.name}=${p.default}` : p.name))
        .join(", ");
      md.appendMarkdown(`\n\n\`${def.name}(${params}) =>\``);
    }

    if (def.kind === "import") {
      md.appendMarkdown(`\n\nImports plugin: \`${def.node.plugin}\``);
    }

    return new vscode.Hover(md, range);
  }
}

// ── Definition Provider ─────────────────────────────────────────
class DefinitionProvider {
  constructor(index) {
    this.index = index;
  }

  provideDefinition(doc, pos, token) {
    const range = doc.getWordRangeAtPosition(pos, /[a-zA-Z_$]\w*/);
    if (!range) return null;
    const word = doc.getText(range);

    // search current doc first
    const local = getSymbolsFromDoc(doc.getText()).filter(
      (s) => s.name === word,
    );
    if (local.length) {
      const s = local[0];
      const line = s.node.line - 1;
      return new vscode.Location(
        doc.uri,
        new vscode.Range(line, 0, line, s.name.length),
      );
    }

    // search index
    const defs = this.index.getDefinition(word);
    if (!defs.length) return null;
    return defs.map((d) => {
      const line = d.line - 1;
      return new vscode.Location(
        d.uri,
        new vscode.Range(line, 0, line, word.length),
      );
    });
  }
}

// ── References Provider ──────────────────────────────────────────
class ReferencesProvider {
  constructor(index) {
    this.index = index;
  }

  async provideReferences(doc, pos, ctx, token) {
    const range = doc.getWordRangeAtPosition(pos, /[a-zA-Z_$]\w*/);
    if (!range) return null;
    const word = doc.getText(range);
    const results = [];

    // search all open + workspace docs
    const files = new Set();
    files.add(doc.uri.toString());
    for (const [uri] of this.index.fileSymbols) files.add(uri);

    for (const uriStr of files) {
      let text;
      if (uriStr === doc.uri.toString()) {
        text = doc.getText();
      } else {
        try {
          const d = await vscode.workspace.openTextDocument(
            vscode.Uri.parse(uriStr),
          );
          text = d.getText();
        } catch {
          continue;
        }
      }
      const lines = text.split(/\r?\n/);
      // match [word] or [word.method] or word. or standalone
      const re = new RegExp(`\\[${escapeRegex(word)}(?:\\.|\\]|\\b)`, "g");
      const re2 = new RegExp(`\\b${escapeRegex(word)}\\.`, "g");
      lines.forEach((line, i) => {
        let m;
        while ((m = re.exec(line))) {
          results.push(
            new vscode.Location(
              uriStr.startsWith("file:") ? vscode.Uri.parse(uriStr) : doc.uri,
              new vscode.Range(i, m.index, i, m.index + word.length),
            ),
          );
        }
        while ((m = re2.exec(line))) {
          if (
            line
              .slice(m.index)
              .match(new RegExp(`\\b${escapeRegex(word)}\\s*\\.`))
          ) {
            results.push(
              new vscode.Location(
                uriStr.startsWith("file:") ? vscode.Uri.parse(uriStr) : doc.uri,
                new vscode.Range(i, m.index, i, m.index + word.length),
              ),
            );
          }
        }
      });
    }
    return results;
  }
}

// ── Rename Provider ──────────────────────────────────────────────
class RenameProvider {
  constructor(index) {
    this.index = index;
  }

  async provideRenameEdits(doc, pos, newName, token) {
    const range = doc.getWordRangeAtPosition(pos, /[a-zA-Z_$]\w*/);
    if (!range) return null;
    const word = doc.getText(range);
    if (!/^[a-zA-Z_$]\w*$/.test(newName)) return null;

    const edit = new vscode.WorkspaceEdit();
    const refs = await new ReferencesProvider(this.index).provideReferences(
      doc,
      pos,
      { includeDeclaration: true },
      token,
    );
    if (!refs) return null;

    for (const loc of refs) {
      edit.replace(loc.uri, loc.range, newName);
    }
    return edit;
  }

  prepareRename(doc, pos, token) {
    const range = doc.getWordRangeAtPosition(pos, /[a-zA-Z_$]\w*/);
    if (!range) return null;
    const word = doc.getText(range);
    return { range, placeholder: word };
  }
}

// ── Document Symbols ─────────────────────────────────────────────
class DocumentSymbolProvider {
  provideDocumentSymbols(doc, token) {
    const nodes = parse(doc.getText());
    const symbols = [];
    const kindMap = {
      table: vscode.SymbolKind.Class,
      function: vscode.SymbolKind.Function,
      assignment: vscode.SymbolKind.Variable,
      import: vscode.SymbolKind.Module,
      meta: vscode.SymbolKind.Property,
      output: vscode.SymbolKind.Field,
    };
    for (const node of nodes) {
      if (node.type === "blank" || node.type === "comment") continue;
      const name =
        node.name || node.type === "output"
          ? "$output"
          : node.type === "meta"
            ? "$meta"
            : node.name;
      if (!name) continue;
      const range = new vscode.Range(
        node.line - 1,
        0,
        (node.endLine || node.line) - 1,
        0,
      );
      const sel = new vscode.Range(
        node.line - 1,
        0,
        node.line - 1,
        name.length,
      );
      symbols.push(
        new vscode.DocumentSymbol(
          name,
          "",
          kindMap[node.type] || vscode.SymbolKind.Variable,
          range,
          sel,
        ),
      );
    }
    return symbols;
  }
}

// ── Workspace Symbols ────────────────────────────────────────────
class WorkspaceSymbolProvider {
  constructor(index) {
    this.index = index;
  }

  async provideWorkspaceSymbols(query, token) {
    await this.index.rebuild();
    const all = this.index.toSymbolInformation();
    if (!query) return all;
    const q = query.toLowerCase();
    return all.filter((s) => s.name.toLowerCase().includes(q));
  }
}

// ── Diagnostics ─────────────────────────────────────────────────
class DiagnosticsProvider {
  constructor(index) {
    this.index = index;
  }

  async computeDiagnostics(doc) {
    const cfg = vscode.workspace.getConfiguration("perchance");
    if (!cfg.get("lint.enabled", true)) return [];
    const diagnostics = [];
    const text = doc.getText();
    const nodes = parse(text);

    // collect defined names
    const defined = new Set();
    for (const n of nodes) {
      if (n.name) defined.add(n.name);
    }
    // also from index
    await this.index.rebuild();
    for (const name of this.index.getAllDefinedNames()) defined.add(name);

    const strict = cfg.get("lint.strictMode", false);
    const toDiag = (msg, line, severity) => ({
      message: msg,
      range: new vscode.Range(line, 0, line, 999),
      severity:
        strict && severity === vscode.DiagnosticSeverity.Warning
          ? vscode.DiagnosticSeverity.Error
          : severity,
      source: "perchance",
    });

    for (const node of nodes) {
      // unclosed brackets per line
      if (cfg.get("lint.unclosedBrackets", true)) {
        if (node.type === "table") {
          for (const item of node.items) {
            const bal = bracketBalance(item.raw);
            if (bal.brackets !== 0) {
              diagnostics.push(
                toDiag(
                  `Unbalanced [ ] in item (delta ${bal.brackets})`,
                  item.line - 1,
                  vscode.DiagnosticSeverity.Error,
                ),
              );
            }
            if (bal.braces !== 0) {
              diagnostics.push(
                toDiag(
                  `Unbalanced { } in item (delta ${bal.braces})`,
                  item.line - 1,
                  vscode.DiagnosticSeverity.Error,
                ),
              );
            }
          }
        } else if (node.type === "assignment" || node.type === "output") {
          const lineText = doc.lineAt(node.line - 1).text;
          const bal = bracketBalance(lineText);
          if (bal.brackets !== 0)
            diagnostics.push(
              toDiag(
                "Unbalanced [ ]",
                node.line - 1,
                vscode.DiagnosticSeverity.Error,
              ),
            );
          if (bal.braces !== 0)
            diagnostics.push(
              toDiag(
                "Unbalanced { }",
                node.line - 1,
                vscode.DiagnosticSeverity.Error,
              ),
            );
        }
      }

      // undefined tables
      if (cfg.get("lint.undefinedTables", true)) {
        const refs = [];
        if (node.type === "table") {
          for (const item of node.items) refs.push(...item.references);
        } else if (node.type === "output") {
          refs.push(...extractReferences(node.expr));
        } else if (node.type === "assignment") {
          refs.push(...extractReferences(node.value));
        }
        for (const r of refs) {
          if (!defined.has(r) && !BUILTINS.includes(r) && !isGlobalJs(r)) {
            diagnostics.push(
              toDiag(
                `Undefined table or variable: '${r}'`,
                node.line - 1,
                vscode.DiagnosticSeverity.Warning,
              ),
            );
          }
        }
      }

      // invalid weights
      if (cfg.get("lint.invalidWeights", true) && node.type === "table") {
        for (const item of node.items) {
          const wCheck = checkWeightSyntax(item.raw);
          if (wCheck)
            diagnostics.push(
              toDiag(wCheck, item.line - 1, vscode.DiagnosticSeverity.Warning),
            );
        }
      }

      // unreachable branches: ^[false] or ^[0]
      if (cfg.get("lint.unreachableBranches", false) && node.type === "table") {
        for (const item of node.items) {
          if (item.weight && item.weight.type === "dynamic") {
            const e = item.weight.expr.trim();
            if (e === "false" || e === "0") {
              diagnostics.push(
                toDiag(
                  `Unreachable branch: weight is always ${e}`,
                  item.line - 1,
                  vscode.DiagnosticSeverity.Warning,
                ),
              );
            }
          }
        }
      }
    }

    // unused variables (top-level names never referenced)
    if (cfg.get("lint.unusedVariables", true)) {
      const referenced = new Set();
      for (const n of nodes) {
        if (n.type === "table") {
          for (const item of n.items)
            for (const r of item.references) referenced.add(r);
        } else if (n.type === "output") {
          for (const r of extractReferences(n.expr)) referenced.add(r);
        } else if (n.type === "assignment") {
          for (const r of extractReferences(n.value)) referenced.add(r);
        }
      }
      for (const n of nodes) {
        if (
          (n.type === "table" || n.type === "assignment") &&
          n.name !== "$output" &&
          n.name !== "$meta"
        ) {
          if (!referenced.has(n.name)) {
            diagnostics.push(
              toDiag(
                `'${n.name}' is defined but never referenced`,
                n.line - 1,
                vscode.DiagnosticSeverity.Hint,
              ),
            );
          }
        }
      }
    }

    return diagnostics;
  }
}

// ── Formatter ────────────────────────────────────────────────────
class Formatter {
  provideDocumentFormattingEdits(doc, opts, token) {
    const cfg = vscode.workspace.getConfiguration("perchance");
    const indentSize = cfg.get("formatting.indentSize", 2);
    const alignWeights = cfg.get("formatting.alignWeights", false);
    const blockSpacing = cfg.get("formatting.blockSpacing", "one");
    const trimTrailing = cfg.get("formatting.trimTrailingWhitespace", true);
    const finalNewline = cfg.get("formatting.insertFinalNewline", true);

    const nodes = parse(doc.getText());
    const lines = [];

    // Build output respecting block spacing
    const blockNodes = nodes.filter(
      (n) => n.type !== "blank" && n.type !== "comment",
    );
    let lastWasBlock = false;

    for (let idx = 0; idx < nodes.length; idx++) {
      const node = nodes[idx];
      if (node.type === "comment") {
        lines.push(node.text);
        lastWasBlock = false;
        continue;
      }
      if (node.type === "blank") continue; // we manage our own spacing

      // spacing between blocks
      if (lastWasBlock && blockSpacing === "one") lines.push("");
      lastWasBlock = true;

      switch (node.type) {
        case "import":
        case "assignment": {
          lines.push(doc.lineAt(node.line - 1).text.trim());
          break;
        }
        case "meta": {
          lines.push("$meta");
          for (const sk of node.subkeys) {
            lines.push(
              `${" ".repeat(indentSize)}${sk.key}${sk.value ? " = " + sk.value : ""}`,
            );
          }
          break;
        }
        case "output": {
          lines.push(`$output = ${node.expr}`);
          break;
        }
        case "function": {
          const params = node.params
            .map((p) => (p.default ? `${p.name}=${p.default}` : p.name))
            .join(", ");
          lines.push(`${node.name}(${params}) =>`);
          for (const bl of node.body) {
            lines.push(`${" ".repeat(indentSize)}${bl.text}`);
          }
          break;
        }
        case "table": {
          lines.push(node.name);
          if (alignWeights) {
            const formatted = formatTableAligned(node, indentSize);
            lines.push(...formatted);
          } else {
            for (const item of node.items) {
              lines.push(formatItem(item, indentSize));
            }
          }
          break;
        }
      }
    }

    let out = lines.join("\n");

    if (trimTrailing)
      out = out
        .split("\n")
        .map((l) => l.replace(/\s+$/, ""))
        .join("\n");
    if (finalNewline) out += "\n";

    const fullRange = new vscode.Range(
      0,
      0,
      doc.lineCount - 1,
      doc.lineAt(doc.lineCount - 1).text.length,
    );
    return [vscode.TextEdit.replace(fullRange, out)];
  }
}

function formatItem(item, indentSize) {
  let s = " ".repeat(indentSize) + item.text;
  if (item.weight) {
    if (item.weight.type === "static") s += `^${item.weight.value}`;
    else s += `^[${item.weight.expr}]`;
  }
  return s;
}

function formatTableAligned(node, indentSize) {
  // align ^ markers in a column
  const items = node.items;
  let maxLen = 0;
  for (const it of items) {
    const textLen = it.text.length;
    if (textLen > maxLen) maxLen = textLen;
  }
  return items.map((it) => {
    let s = " ".repeat(indentSize) + it.text.padEnd(maxLen);
    if (it.weight) {
      if (it.weight.type === "static") s += `^${it.weight.value}`;
      else s += `^[${it.weight.expr}]`;
    }
    return s;
  });
}

// ── Semantic Tokens ─────────────────────────────────────────────
class SemanticTokensProvider {
  constructor() {
    this.legend = new vscode.SemanticTokensLegend(
      [
        "table",
        "variable",
        "function",
        "method",
        "keyword",
        "string",
        "number",
        "comment",
        "operator",
        "macro",
      ],
      [
        "declaration",
        "definition",
        "readonly",
        "deprecated",
        "modification",
        "documentation",
      ],
    );
  }

  provideDocumentSemanticTokens(doc, token) {
    const cfg = vscode.workspace.getConfiguration("perchance");
    if (!cfg.get("semanticTokens.enabled", true)) return null;

    const builder = new vscode.SemanticTokensBuilder();
    const text = doc.getText();
    const nodes = parse(text);

    // token type indices
    const T = {
      table: 0,
      variable: 1,
      function: 2,
      method: 3,
      keyword: 4,
      string: 5,
      number: 6,
      comment: 7,
      operator: 8,
      macro: 9,
    };

    // Highlight table names (definitions)
    const definedTables = new Set();
    for (const n of nodes) {
      if (n.type === "table") definedTables.add(n.name);
    }

    // Scan line by line for token-level highlighting
    const lines = text.split(/\r?\n/);
    for (let lineIdx = 0; lineIdx < lines.length; lineIdx++) {
      const line = lines[lineIdx];
      // table headers
      const trimmed = line.trimStart();
      const indent = line.length - trimmed.length;
      if (indent === 0) {
        if (/^[A-Za-z_]\w*$/.test(trimmed) && definedTables.has(trimmed)) {
          builder.push(lineIdx, 0, trimmed.length, T.table, 1); // declaration+definition
        }
        if (/^\$meta/.test(trimmed) || /^\$output/.test(trimmed)) {
          builder.push(
            lineIdx,
            0,
            trimmed.indexOf(" ") > 0 ? trimmed.indexOf(" ") : trimmed.length,
            T.keyword,
            1,
          );
        }
      }
      // function names
      const fnMatch = line.match(/^(\w+)\s*\(/);
      if (fnMatch && indent === 0 && line.includes("=>")) {
        builder.push(lineIdx, 0, fnMatch[1].length, T.function, 1);
      }
      // variables in assignments
      const aMatch = line.match(/^\s*(\w+)\s*=/);
      if (aMatch && indent === 0 && !fnMatch) {
        if (!definedTables.has(aMatch[1]) && !aMatch[1].startsWith("$")) {
          builder.push(lineIdx, 0, aMatch[1].length, T.variable, 1);
        }
      }
      // built-in methods inside JS blocks
      for (const m of line.matchAll(
        /\b(selectOne|selectMany|selectUnique|getLength|joinItems|evaluateItem|selectAll)\b/g,
      )) {
        builder.push(lineIdx, m.index, m[0].length, T.method, 0);
      }
      // numbers
      for (const m of line.matchAll(/\b\d+\.?\d*\b/g)) {
        if (line[m.index - 1] !== "." && line[m.index - 1] !== "_") {
          builder.push(lineIdx, m.index, m[0].length, T.number, 0);
        }
      }
      // weight operators
      for (const m of line.matchAll(/\^(\d+|\[)/g)) {
        builder.push(lineIdx, m.index, 1, T.operator, 0);
      }
    }

    return builder.build();
  }

  provideDocumentSemanticTokensEdit(doc, prevEditId, token) {
    return this.provideDocumentSemanticTokens(doc, token);
  }
}

// ── Signature Help ───────────────────────────────────────────────
class SignatureHelpProvider {
  provideSignatureHelp(doc, pos, token, ctx) {
    const line = doc.lineAt(pos).text;
    const before = line.slice(0, pos.character);
    const openParen = before.lastIndexOf("(");
    if (openParen < 0) return null;

    // find method name
    const m = before.slice(0, openParen).match(/(\w+)$/);
    if (!m) return null;
    const methodName = m[1];

    if (!BUILTIN_DOCS[methodName]) return null;
    const d = BUILTIN_DOCS[methodName];

    const sig = new vscode.SignatureInformation(d.sig, d.doc);
    for (const p of d.params) {
      sig.parameters.push(new vscode.ParameterInformation(p.name, p.doc));
    }

    const help = new vscode.SignatureHelp();
    help.signatures = [sig];
    help.activeSignature = 0;
    help.activeParameter = Math.min(
      before.slice(openParen + 1).split(",").length - 1,
      d.params.length,
    );
    return help;
  }
}

// ── Code Actions ─────────────────────────────────────────────────
class CodeActionProvider {
  constructor(index) {
    this.index = index;
  }

  async provideCodeActions(doc, range, ctx, token) {
    const actions = [];
    for (const diag of ctx.diagnostics || []) {
      // Undefined table — offer to create it
      const m = diag.message.match(/Undefined table or variable: '(.+)'/);
      if (m) {
        const name = m[1];
        const action = new vscode.CodeAction(
          `Create table '${name}'`,
          vscode.CodeActionKind.QuickFix,
        );
        action.edit = new vscode.WorkspaceEdit();
        action.edit.createFile(doc.uri, { ignoreIfExists: true });
        // insert at end of doc
        const lastLine = doc.lineCount;
        action.edit.insert(
          doc.uri,
          new vscode.Position(lastLine, 0),
          `\n${name}\n  new item\n`,
        );
        action.isPreferred = true;
        actions.push(action);
      }
    }
    return actions;
  }
}

// ── Helpers ─────────────────────────────────────────────────────
function isInJsBlock(line, char) {
  let depth = 0;
  let inStr = null;
  for (let i = 0; i < char && i < line.length; i++) {
    const c = line[i];
    if (inStr) {
      if (c === "\\") i++;
      else if (c === inStr) inStr = null;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") inStr = c;
    else if (c === "[") depth++;
    else if (c === "]") depth--;
  }
  return depth > 0;
}

function isGlobalJs(name) {
  return [
    "Math",
    "JSON",
    "String",
    "Array",
    "Object",
    "Number",
    "Boolean",
    "Date",
    "console",
    "Promise",
    "window",
    "document",
    "this",
    "root",
    "parseInt",
    "parseFloat",
    "isNaN",
    "NaN",
    "undefined",
    "null",
    "true",
    "false",
  ].includes(name);
}

function checkWeightSyntax(raw) {
  // look for ^ not followed by number, [..], or end-of-item
  const trimmed = raw.trim();
  const caretIdx = trimmed.indexOf("^");
  if (caretIdx < 0) return null;
  // find caret outside brackets
  let depth = 0;
  let inStr = null;
  for (let i = 0; i < trimmed.length; i++) {
    const c = trimmed[i];
    if (inStr) {
      if (c === "\\") i++;
      else if (c === inStr) inStr = null;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") inStr = c;
    else if (c === "[") depth++;
    else if (c === "]") depth--;
    else if (c === "{") {
    } // alternation handled elsewhere
    else if (c === "^" && depth === 0) {
      const after = trimmed.slice(i + 1).trim();
      if (after === "" || /^\d+$/.test(after) || /^\[/.test(after)) return null;
      return `Malformed weight: '${after}' after ^ — expected a number, [expression], or nothing`;
    }
  }
  return null;
}

function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function shortPath(uri) {
  if (typeof uri === "string") {
    const parts = uri.split("/");
    return parts.slice(-2).join("/");
  }
  return vscode.workspace.asRelativePath(uri);
}

module.exports = {
  CompletionProvider,
  HoverProvider,
  DefinitionProvider,
  ReferencesProvider,
  RenameProvider,
  DocumentSymbolProvider,
  WorkspaceSymbolProvider,
  DiagnosticsProvider,
  Formatter,
  SemanticTokensProvider,
  SignatureHelpProvider,
  CodeActionProvider,
  getSymbolsFromDoc,
  BUILTIN_DOCS,
};
