"use strict";

const vscode = require("vscode");
const { WorkspaceIndex } = require("./index");
const {
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
} = require("./language");
const { GraphView } = require("./graph");
const { TableExplorerProvider } = require("./explorer");
const cmds = require("./commands");

let index;
let diagnosticsCollection;
let diagProvider;
let saveTimer;

function activate(context) {
  index = new WorkspaceIndex();

  // ── Diagnostics collection ─────────────────────────────────────
  diagnosticsCollection =
    vscode.languages.createDiagnosticCollection("perchance");
  diagProvider = new DiagnosticsProvider(index);
  context.subscriptions.push(diagnosticsCollection);

  // ── Register providers ─────────────────────────────────────────
  const sel = { scheme: "file", language: "perchance" };
  const triggerChars = [".", "[", "{", "^"];

  context.subscriptions.push(
    vscode.languages.registerCompletionItemProvider(
      sel,
      new CompletionProvider(index),
      ...triggerChars,
    ),
    vscode.languages.registerHoverProvider(sel, new HoverProvider(index)),
    vscode.languages.registerDefinitionProvider(
      sel,
      new DefinitionProvider(index),
    ),
    vscode.languages.registerReferenceProvider(
      sel,
      new ReferencesProvider(index),
    ),
    vscode.languages.registerRenameProvider(sel, new RenameProvider(index)),
    vscode.languages.registerDocumentSymbolProvider(
      sel,
      new DocumentSymbolProvider(),
    ),
    vscode.languages.registerWorkspaceSymbolProvider(
      new WorkspaceSymbolProvider(index),
    ),
    vscode.languages.registerSignatureHelpProvider(
      sel,
      new SignatureHelpProvider(),
      "(",
      ",",
    ),
    vscode.languages.registerCodeActionsProvider(
      sel,
      new CodeActionProvider(index),
    ),
    vscode.languages.registerDocumentSemanticTokensProvider(
      sel,
      new SemanticTokensProvider(),
      new vscode.SemanticTokensLegend(
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
      ),
    ),
  );

  // Formatter (registered as default formatter)
  context.subscriptions.push(
    vscode.languages.registerDocumentFormattingEditProvider(
      sel,
      new Formatter(),
    ),
  );

  // ── Table Explorer tree view ───────────────────────────────────
  const explorerProvider = new TableExplorerProvider(index);
  const treeView = vscode.window.createTreeView("perchance.tableExplorer", {
    treeDataProvider: explorerProvider,
    showCollapseAll: true,
  });
  context.subscriptions.push(treeView);

  // ── Graph view ─────────────────────────────────────────────────
  const graphView = new GraphView(context, index);

  // ── Commands ───────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand("perchance.preview", (uri) =>
      cmds.previewCommand(index, uri),
    ),
    vscode.commands.registerCommand("perchance.previewSeeded", (uri) =>
      cmds.previewSeededCommand(index, uri),
    ),
    vscode.commands.registerCommand("perchance.generateMulti", (uri) =>
      cmds.generateMultiCommand(index, uri),
    ),
    vscode.commands.registerCommand("perchance.toggleDebug", () =>
      cmds.toggleDebugCommand(),
    ),
    vscode.commands.registerCommand("perchance.showGraph", (uri) =>
      graphView.show(uri || vscode.window.activeTextEditor?.document.uri),
    ),
    vscode.commands.registerCommand("perchance.organizeTables", () =>
      cmds.organizeTablesCommand(index),
    ),
    vscode.commands.registerCommand("perchance.collapseDuplicates", () =>
      cmds.collapseDuplicatesCommand(index),
    ),
    vscode.commands.registerCommand("perchance.formatDocument", () =>
      cmds.formatDocumentCommand(),
    ),
    vscode.commands.registerCommand("perchance.rebuildIndex", () =>
      cmds.rebuildIndexCommand(index),
    ),
    vscode.commands.registerCommand("perchance.exportJson", (uri) =>
      cmds.exportJsonCommand(index, uri),
    ),
    vscode.commands.registerCommand(
      "perchance.createTest",
      (uri, line, length) => cmds.createTestCommand(index, uri, line, length),
    ),
    vscode.commands.registerCommand("perchance.createTable", (uri) =>
      cmds.createTableCommand(index, uri),
    ),
    vscode.commands.registerCommand(
      "perchance.tableExplorer.goto",
      (uri, line, length) => {
        vscode.window.showTextDocument(uri, {
          selection: new vscode.Range(line, 0, line, length || 0),
        });
      },
    ),
    vscode.commands.registerCommand("perchance.tableExplorer.refresh", () =>
      explorerProvider.refresh(),
    ),
  );

  // ── Diagnostics on change (debounced) ──────────────────────────
  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (e.document.languageId !== "perchance") return;
      index.setDirty();
      scheduleDiagnostics(e.document);
    }),
  );
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (doc.languageId !== "perchance") return;
      index.parseDocument(doc.getText(), doc.uri);
      index.setDirty();
      scheduleDiagnostics(doc);
      explorerProvider.refresh();
    }),
  );
  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((doc) => {
      if (doc.languageId !== "perchance") return;
      index.setDirty();
      scheduleDiagnostics(doc);
    }),
  );
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      if (!editor) return;
      if (editor.document.languageId !== "perchance") return;
      scheduleDiagnostics(editor.document);
      explorerProvider.refresh();
    }),
  );

  // ── File watcher for external changes ──────────────────────────
  context.subscriptions.push(
    vscode.workspace.onDidCreateFiles(() => {
      index.setDirty();
    }),
    vscode.workspace.onDidDeleteFiles(() => {
      index.setDirty();
    }),
  );

  // ── Trigger initial diagnostics ───────────────────────────────
  if (
    vscode.window.activeTextEditor &&
    vscode.window.activeTextEditor.document.languageId === "perchance"
  ) {
    scheduleDiagnostics(vscode.window.activeTextEditor.document);
    explorerProvider.refresh();
  }

  // ── Status bar item ────────────────────────────────────────────
  const statusItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Right,
    100,
  );
  statusItem.text = "$(list-tree) Perchance";
  statusItem.tooltip = "Perchance PJS Support";
  statusItem.command = "perchance.rebuildIndex";
  statusItem.show();
  context.subscriptions.push(statusItem);

  console.log("Perchance PJS Support extension activated.");
}

function scheduleDiagnostics(doc) {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    try {
      const diags = await diagProvider.computeDiagnostics(doc);
      diagnosticsCollection.set(doc.uri, diags);
    } catch (e) {
      // ignore
    }
  }, 300);
}

function deactivate() {
  if (saveTimer) clearTimeout(saveTimer);
}

module.exports = { activate, deactivate };
