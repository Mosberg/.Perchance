const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");
const { workspaceIndex } = require("./index");

function registerCommands(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("perchance.rebuildIndex", async () => {
      workspaceIndex.clear();
      const docs = vscode.workspace.textDocuments.filter(
        (d) => d.languageId === LANGUAGE_ID,
      );
      docs.forEach((d) => workspaceIndex.update(d.uri, d.getText()));
      vscode.window.showInformationMessage(
        "Perchance workspace index rebuilt.",
      );
    }),
  );
}

module.exports = {
  registerCommands,
};
