"use strict";

const vscode = require("vscode");
const { parse } = require("./parser");
const { runPreview, runPreviewN, createRng } = require("./preview");

/**
 * Command handlers for the Perchance extension.
 */

// ── Preview Output ────────────────────────────────────────────────
async function previewCommand(index, docUri) {
  const doc = docUri
    ? await vscode.workspace.openTextDocument(docUri)
    : vscode.window.activeTextEditor?.document;
  if (!doc) {
    vscode.window.showWarningMessage("No active Perchance file.");
    return;
  }

  const cfg = vscode.workspace.getConfiguration("perchance");
  const seed = cfg.get("preview.defaultSeed", "") || undefined;
  const debug = cfg.get("preview.debugTrace", false);
  const format = cfg.get("preview.outputFormat", "plain");

  await showPreviewPanel(doc, seed, debug, format);
}

// ── Preview with Seed ────────────────────────────────────────────
async function previewSeededCommand(index, docUri) {
  const doc = docUri
    ? await vscode.workspace.openTextDocument(docUri)
    : vscode.window.activeTextEditor?.document;
  if (!doc) return;

  const seed = await vscode.window.showInputBox({
    prompt: "Enter a seed (string or number)",
    placeHolder: "e.g. 42 or myseed",
  });
  if (seed === undefined) return;
  const cfg = vscode.workspace.getConfiguration("perchance");
  await showPreviewPanel(
    doc,
    seed,
    cfg.get("preview.debugTrace", false),
    cfg.get("preview.outputFormat", "plain"),
    true,
  );
}

// ── Generate Multiple ────────────────────────────────────────────
async function generateMultiCommand(index, docUri) {
  const doc = docUri
    ? await vscode.workspace.openTextDocument(docUri)
    : vscode.window.activeTextEditor?.document;
  if (!doc) return;

  const cfg = vscode.workspace.getConfiguration("perchance");
  const defaultCount = cfg.get("preview.multiRunCount", 10);
  const countStr = await vscode.window.showInputBox({
    prompt: "How many outputs?",
    value: String(defaultCount),
  });
  if (!countStr) return;
  const count = parseInt(countStr, 10) || 1;
  const seed = cfg.get("preview.defaultSeed", "") || undefined;
  const debug = cfg.get("preview.debugTrace", false);

  const results = runPreviewN(doc.getText(), count, { seed, debug });

  const panel = vscode.window.createWebviewPanel(
    "perchance.multiPreview",
    `Perchance: ${count} Outputs`,
    vscode.ViewColumn.Two,
    { enableScripts: true },
  );
  const format = cfg.get("preview.outputFormat", "plain");
  panel.webview.html = renderMultiOutput(results, format, doc.fileName);
}

async function showPreviewPanel(doc, seed, debug, format, isSeeded = false) {
  const { output, trace } = runPreview(doc.getText(), { seed, debug });

  const panel = vscode.window.createWebviewPanel(
    "perchance.preview",
    `Perchance Preview${isSeeded && seed ? ` (seed: ${seed})` : ""}`,
    vscode.ViewColumn.Two,
    { enableScripts: true },
  );
  panel.webview.html = renderOutput(
    output,
    format,
    doc.fileName,
    seed,
    trace,
    debug,
  );
}

function renderOutput(output, format, fileName, seed, trace, debug) {
  const escaped = escapeHtml(output);
  let body = "";
  if (format === "html") {
    body = `<div class="output-html">${output}</div>`;
  } else if (format === "markdown") {
    body = `<div class="output-md"><pre>${escaped}</pre></div>`;
  } else {
    body = `<pre class="output-plain">${escaped}</pre>`;
  }

  const traceHtml =
    debug && trace.length
      ? `<details class="trace"><summary>Debug Trace (${trace.length} entries)</summary><pre>${escapeHtml(trace.join("\n"))}</pre></details>`
      : "";

  return `<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body { font-family: var(--vscode-editor-font-family, monospace); padding: 16px; color: var(--vscode-editor-foreground); background: var(--vscode-editor-background); }
  .header { margin-bottom: 12px; font-size: 12px; opacity: 0.7; }
  pre { white-space: pre-wrap; word-wrap: break-word; font-family: inherit; }
  .trace { margin-top: 16px; border-top: 1px solid var(--vscode-panel-border); padding-top: 12px; }
  .trace summary { cursor: pointer; font-size: 12px; opacity: 0.8; }
  .trace pre { font-size: 11px; opacity: 0.7; }
  .output-html { line-height: 1.5; }
</style>
</head><body>
<div class="header">${escapeHtml(fileName)}${seed ? " · seed: " + escapeHtml(String(seed)) : ""}</div>
${body}
${traceHtml}
<script>
  // keyboard: 'r' to re-run (asks extension)
  document.addEventListener('keydown', e => { if (e.key === 'r' && e.ctrlKey) { e.preventDefault(); } });
</script>
</body></html>`;
}

function renderMultiOutput(results, format, fileName) {
  const items = results
    .map((r, i) => {
      const e = escapeHtml(r);
      return `<div class="multi-item"><div class="multi-num">#${i + 1}</div><pre>${e}</pre></div>`;
    })
    .join("");
  return `<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body { font-family: var(--vscode-editor-font-family, monospace); padding: 16px; color: var(--vscode-editor-foreground); background: var(--vscode-editor-background); }
  h2 { margin: 0 0 12px 0; font-size: 14px; }
  .multi-item { display: flex; gap: 12px; margin-bottom: 8px; padding: 8px; border: 1px solid var(--vscode-panel-border); border-radius: 4px; }
  .multi-num { font-size: 11px; opacity: 0.5; min-width: 30px; padding-top: 2px; }
  .multi-item pre { white-space: pre-wrap; word-wrap: break-word; margin: 0; font-family: inherit; }
</style>
</head><body>
<h2>${results.length} outputs from ${escapeHtml(fileName)}</h2>
${items}
</body></html>`;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Toggle Debug ─────────────────────────────────────────────────
function toggleDebugCommand() {
  const cfg = vscode.workspace.getConfiguration("perchance");
  const cur = cfg.get("preview.debugTrace", false);
  cfg
    .update("preview.debugTrace", !cur, vscode.ConfigurationTarget.Global)
    .then(() => {
      vscode.window.showInformationMessage(
        `Perchance debug trace: ${!cur ? "ON" : "OFF"}`,
      );
    });
}

// ── Organize Tables ──────────────────────────────────────────────
function organizeTablesCommand(index) {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return;
  const doc = editor.document;
  if (doc.languageId !== "perchance") {
    vscode.window.showWarningMessage("Not a Perchance file.");
    return;
  }

  const nodes = parse(doc.getText());
  const edits = [];

  for (const node of nodes) {
    if (node.type !== "table") continue;
    // sort items alphabetically (case-insensitive), preserve weights
    const sorted = [...node.items].sort((a, b) =>
      a.text.localeCompare(b.text, undefined, { sensitivity: "base" }),
    );
    // check if already sorted
    let changed = false;
    for (let i = 0; i < sorted.length; i++) {
      if (sorted[i].line !== node.items[i].line) {
        changed = true;
        break;
      }
    }
    if (!changed) continue;
    // build replacement text
    const startLine = node.items[0].line - 1;
    const endLine = node.items[node.items.length - 1].line - 1;
    const indent = " ".repeat(
      vscode.workspace
        .getConfiguration("perchance")
        .get("formatting.indentSize", 2),
    );
    const newText = sorted
      .map((it) => {
        let s = indent + it.text;
        if (it.weight) {
          if (it.weight.type === "static") s += `^${it.weight.value}`;
          else s += `^[${it.weight.expr}]`;
        }
        return s;
      })
      .join("\n");
    const range = new vscode.Range(
      startLine,
      0,
      endLine,
      doc.lineAt(endLine).text.length,
    );
    edits.push(vscode.TextEdit.replace(range, newText));
  }

  if (!edits.length) {
    vscode.window.showInformationMessage("Tables already organized.");
    return;
  }

  const we = new vscode.WorkspaceEdit();
  we.set(doc.uri, edits);
  vscode.workspace.applyEdit(we).then(() => {
    vscode.window.showInformationMessage(`Organized ${edits.length} table(s).`);
  });
}

// ── Collapse Duplicates ──────────────────────────────────────────
function collapseDuplicatesCommand(index) {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return;
  const doc = editor.document;
  if (doc.languageId !== "perchance") return;

  const nodes = parse(doc.getText());
  const edits = [];

  for (const node of nodes) {
    if (node.type !== "table") continue;
    // group by text
    const groups = new Map();
    for (const it of node.items) {
      if (!groups.has(it.text)) groups.set(it.text, []);
      groups.get(it.text).push(it);
    }
    let changed = false;
    const newItems = [];
    for (const [text, items] of groups) {
      if (items.length > 1) {
        changed = true;
        // merge weights: sum static weights, keep first dynamic
        let totalStatic = 0;
        let dynamicExpr = null;
        for (const it of items) {
          if (it.weight && it.weight.type === "static")
            totalStatic += it.weight.value;
          else if (it.weight && it.weight.type === "dynamic")
            dynamicExpr = it.weight.expr;
        }
        newItems.push({
          text,
          weight: dynamicExpr
            ? { type: "dynamic", expr: dynamicExpr }
            : totalStatic > 0
              ? { type: "static", value: totalStatic }
              : null,
          line: items[0].line,
        });
      } else {
        newItems.push(items[0]);
      }
    }
    if (!changed) continue;
    const startLine = node.items[0].line - 1;
    const endLine = node.items[node.items.length - 1].line - 1;
    const indent = " ".repeat(
      vscode.workspace
        .getConfiguration("perchance")
        .get("formatting.indentSize", 2),
    );
    const newText = newItems
      .map((it) => {
        let s = indent + it.text;
        if (it.weight) {
          if (it.weight.type === "static") s += `^${it.weight.value}`;
          else s += `^[${it.weight.expr}]`;
        }
        return s;
      })
      .join("\n");
    edits.push(
      vscode.TextEdit.replace(
        new vscode.Range(
          startLine,
          0,
          endLine,
          doc.lineAt(endLine).text.length,
        ),
        newText,
      ),
    );
  }

  if (!edits.length) {
    vscode.window.showInformationMessage("No duplicates found.");
    return;
  }
  const we = new vscode.WorkspaceEdit();
  we.set(doc.uri, edits);
  vscode.workspace
    .applyEdit(we)
    .then(() =>
      vscode.window.showInformationMessage(
        `Collapsed duplicates in ${edits.length} table(s).`,
      ),
    );
}

// ── Rebuild Index ────────────────────────────────────────────────
async function rebuildIndexCommand(index) {
  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "Indexing Perchance files...",
    },
    async () => {
      await index.rebuild(true);
    },
  );
  vscode.window.showInformationMessage("Perchance workspace index rebuilt.");
}

// ── Export to JSON ────────────────────────────────────────────────
async function exportJsonCommand(index, docUri) {
  const doc = docUri
    ? await vscode.workspace.openTextDocument(docUri)
    : vscode.window.activeTextEditor?.document;
  if (!doc) return;
  const nodes = parse(doc.getText());
  const json = {
    file: doc.fileName,
    meta: null,
    tables: {},
    variables: {},
    functions: [],
    imports: [],
    output: null,
  };
  for (const n of nodes) {
    switch (n.type) {
      case "meta":
        json.meta = {};
        for (const sk of n.subkeys) json.meta[sk.key] = sk.value;
        break;
      case "table":
        json.tables[n.name] = n.items.map((it) => ({
          text: it.text,
          weight: it.weight
            ? it.weight.type === "static"
              ? it.weight.value
              : `[${it.weight.expr}]`
            : null,
          references: it.references,
        }));
        break;
      case "assignment":
        json.variables[n.name] = n.value;
        break;
      case "function":
        json.functions.push({ name: n.name, params: n.params });
        break;
      case "import":
        json.imports.push({ name: n.name, plugin: n.plugin });
        break;
      case "output":
        json.output = n.expr;
        break;
    }
  }
  const text = JSON.stringify(json, null, 2);
  const uri = vscode.Uri.parse("untitled:perchance-export.json");
  const newDoc = await vscode.workspace.openTextDocument(uri);
  const edit = new vscode.WorkspaceEdit();
  edit.insert(uri, new vscode.Position(0, 0), text);
  await vscode.workspace.applyEdit(edit);
  await vscode.window.showTextDocument(newDoc, { preview: false });
}

// ── Create Test ──────────────────────────────────────────────────
async function createTestCommand(index, docUri, line, length) {
  const doc = docUri
    ? await vscode.workspace.openTextDocument(docUri)
    : vscode.window.activeTextEditor?.document;
  if (!doc) return;

  // Find the table at the given line (or nearest above)
  const nodes = parse(doc.getText());
  let table = null;
  for (const n of nodes) {
    if (n.type === "table" && (line === undefined || n.line === line + 1)) {
      table = n;
      break;
    }
  }
  if (!table) {
    // find any table
    table = nodes.find((n) => n.type === "table");
  }
  if (!table) {
    vscode.window.showWarningMessage("No table found to test.");
    return;
  }

  // Generate a few sample outputs
  const sampleText = doc.getText();
  const results = runPreviewN(sampleText, 5);
  // try to generate from this specific table
  let samples = [];
  try {
    const { Interpreter } = require("./preview");
    const interp = new Interpreter(parse(sampleText), { seed: "test" });
    for (let i = 0; i < 5; i++) {
      interp._depth = 0;
      samples.push(interp.selectFromTable(table.name));
    }
  } catch {
    samples = ["(error)"];
  }

  const testContent = [
    `// Test for table: ${table.name}`,
    `// File: ${doc.fileName}`,
    `// Generated: ${new Date().toISOString()}`,
    ``,
    `// Sample outputs (seed: "test"):`,
    ...samples.map((s, i) => `//   ${i + 1}. ${s.replace(/\n/g, " ")}`),
    ``,
    `// Assertions:`,
    `// - Table has ${table.items.length} items`,
    `// - Each output should be one of the items`,
    ``,
    `const { parse } = require('./src/parser');`,
    `const { Interpreter } = require('./src/preview');`,
    ``,
    `const assert = require('assert');`,
    `const fs = require('fs');`,
    `const path = require('path');`,
    ``,
    `const text = fs.readFileSync(__dirname + '/${path.basename(doc.fileName)}', 'utf-8');`,
    `const nodes = parse(text);`,
    `const table = nodes.find(n => n.type === 'table' && n.name === '${table.name}');`,
    ``,
    `assert.ok(table, 'Table ${table.name} should exist');`,
    `assert.strictEqual(table.items.length, ${table.items.length}, 'Item count should match');`,
    ``,
    `for (let i = 0; i < 100; i++) {`,
    `  const interp = new Interpreter(nodes, { seed: 'test-' + i });`,
    `  interp._depth = 0;`,
    `  const result = interp.selectFromTable('${table.name}');`,
    `  assert.ok(result, 'Output should not be empty (run ' + i + ')');`,
    `}`,
    ``,
    `console.log('✓ All tests passed for table ${table.name}');`,
  ].join("\n");

  const testUri = vscode.Uri.parse(`untitled:test-${table.name}.test.js`);
  const newDoc = await vscode.workspace.openTextDocument(testUri);
  const edit = new vscode.WorkspaceEdit();
  edit.insert(testUri, new vscode.Position(0, 0), testContent);
  await vscode.workspace.applyEdit(edit);
  await vscode.window.showTextDocument(newDoc, { preview: false });
}

// ── Create New Table ─────────────────────────────────────────────
async function createTableCommand(index, docUri) {
  const name = await vscode.window.showInputBox({
    prompt: "Table name",
    placeHolder: "e.g. npc, adjective, loot",
  });
  if (!name) return;
  if (!/^[a-zA-Z_]\w*$/.test(name)) {
    vscode.window.showErrorMessage("Invalid name.");
    return;
  }

  const editor = vscode.window.activeTextEditor;
  if (!editor) return;
  const doc = editor.document;
  const indent = " ".repeat(
    vscode.workspace
      .getConfiguration("perchance")
      .get("formatting.indentSize", 2),
  );

  const stub = `\n${name}\n${indent}item one\n${indent}item two\n${indent}item three\n`;
  const pos = new vscode.Position(doc.lineCount, 0);
  await editor.edit((e) => e.insert(pos, stub));
  vscode.window.showInformationMessage(`Created table '${name}'.`);
}

// ── Format Document ──────────────────────────────────────────────
function formatDocumentCommand() {
  vscode.commands.executeCommand("editor.action.formatDocument");
}

module.exports = {
  previewCommand,
  previewSeededCommand,
  generateMultiCommand,
  toggleDebugCommand,
  organizeTablesCommand,
  collapseDuplicatesCommand,
  rebuildIndexCommand,
  exportJsonCommand,
  createTestCommand,
  createTableCommand,
  formatDocumentCommand,
};
