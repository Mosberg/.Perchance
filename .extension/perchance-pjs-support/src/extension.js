const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");
const { registerCompletion } = require("./completion");
const { registerHover } = require("./hover");
const { registerDefinition } = require("./definition");
const { registerReferences } = require("./references");
const { registerDocumentSymbols } = require("./symbols");
const { registerFormatter } = require("./formatter");
const { registerRename } = require("./rename");
const { registerSignatureHelp } = require("./signature");
const { registerCodeActions } = require("./codeActions");
const { registerFolding } = require("./folding");
const { registerWorkspaceIndex } = require("./workspaceIndex");
const { registerPreviewCommands } = require("./preview");
const { registerGraphCommand } = require("./graphView");
const { registerExplorer } = require("./explorer");
const { refreshDiagnostics, clearDiagnostics } = require("./diagnostics");
const { indexDocument } = require("./index");

function activate(context) {
  registerWorkspaceIndex(context);
  registerCompletion(context);
  registerHover(context);
  registerDefinition(context);
  registerReferences(context);
  registerDocumentSymbols(context);
  registerFormatter(context);
  registerRename(context);
  registerSignatureHelp(context);
  registerCodeActions(context);
  registerFolding(context);
  registerPreviewCommands(context);
  registerGraphCommand(context);
  registerExplorer(context);

  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((doc) => {
      if (doc.languageId === LANGUAGE_ID) {
        indexDocument(doc);
        refreshDiagnostics(doc);
      }
    }),
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (e.document.languageId === LANGUAGE_ID) {
        indexDocument(e.document);
        refreshDiagnostics(e.document);
      }
    }),
  );

  context.subscriptions.push(
    vscode.workspace.onDidCloseTextDocument((doc) => {
      if (doc.languageId === LANGUAGE_ID) {
        clearDiagnostics(doc);
      }
    }),
  );
}

function deactivate() {}

module.exports = {
  activate,
  deactivate,
};
