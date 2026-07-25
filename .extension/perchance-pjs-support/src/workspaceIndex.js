const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");
const { indexDocument, workspaceIndex } = require("./index");

function registerWorkspaceIndex(context) {
  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((doc) => {
      if (doc.languageId === LANGUAGE_ID) {
        indexDocument(doc);
      }
    }),
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (e.document.languageId === LANGUAGE_ID) {
        indexDocument(e.document);
      }
    }),
  );

  context.subscriptions.push(
    vscode.workspace.onDidCloseTextDocument((doc) => {
      if (doc.languageId === LANGUAGE_ID) {
        workspaceIndex.documents.delete(doc.uri.toString());
      }
    }),
  );
}

module.exports = {
  registerWorkspaceIndex,
};
