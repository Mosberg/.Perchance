const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");
const { workspaceIndex } = require("./index");

function registerCompletion(context) {
  const provider = {
    provideCompletionItems(document, position) {
      if (document.languageId !== LANGUAGE_ID) return;

      const items = [];
      const index = workspaceIndex.get(document.uri);
      const allTables = workspaceIndex.getAllTables();

      // Table names
      for (const name of allTables.keys()) {
        items.push(
          new vscode.CompletionItem(name, vscode.CompletionItemKind.Function),
        );
      }

      // Built-in methods
      [
        "selectOne",
        "selectMany",
        "selectUnique",
        "getLength",
        "selectAll",
        "evaluateItem",
        "joinItems",
      ].forEach((method) => {
        const item = new vscode.CompletionItem(
          `.${method}`,
          vscode.CompletionItemKind.Method,
        );
        item.insertText = method;
        items.push(item);
      });

      // Special blocks
      ["$meta", "$output"].forEach((name) => {
        items.push(
          new vscode.CompletionItem(name, vscode.CompletionItemKind.Keyword),
        );
      });

      return items;
    },
  };

  context.subscriptions.push(
    vscode.languages.registerCompletionItemProvider(
      LANGUAGE_ID,
      provider,
      "[",
      "{",
      "$",
    ),
  );
}

module.exports = {
  registerCompletion,
};
