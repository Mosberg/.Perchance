const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");
const { workspaceIndex } = require("./index");

function registerDefinition(context) {
  const provider = {
    provideDefinition(document, position) {
      if (document.languageId !== LANGUAGE_ID) return;

      const wordRange = document.getWordRangeAtPosition(position, /[\w$]+/);
      if (!wordRange) return;

      const word = document.getText(wordRange);
      const allTables = workspaceIndex.getAllTables();

      if (!allTables.has(word)) return;

      const locations = [];
      for (const table of allTables.get(word)) {
        const uri = document.uri;
        const range = new vscode.Range(table.line, 0, table.line, 1000);
        locations.push(new vscode.Location(uri, range));
      }

      return locations;
    },
  };

  context.subscriptions.push(
    vscode.languages.registerDefinitionProvider(LANGUAGE_ID, provider),
  );
}

module.exports = {
  registerDefinition,
};
