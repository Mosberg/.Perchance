const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");
const { parseDocument } = require("./parser");

function registerDocumentSymbols(context) {
  const provider = {
    provideDocumentSymbols(document) {
      if (document.languageId !== LANGUAGE_ID) return [];

      const ast = parseDocument(document.getText());
      const symbols = [];

      function visit(node) {
        if (node.type === "table") {
          symbols.push(
            new vscode.DocumentSymbol(
              node.name,
              "table",
              vscode.SymbolKind.Function,
              new vscode.Range(node.line, 0, node.line, 1000),
              new vscode.Range(node.line, 0, node.line, 1000),
            ),
          );
        } else if (node.type === "function") {
          symbols.push(
            new vscode.DocumentSymbol(
              node.name,
              "function",
              vscode.SymbolKind.Function,
              new vscode.Range(node.line, 0, node.line, 1000),
              new vscode.Range(node.line, 0, node.line, 1000),
            ),
          );
        } else if (node.type === "assignment") {
          symbols.push(
            new vscode.DocumentSymbol(
              node.name,
              "assignment",
              vscode.SymbolKind.Variable,
              new vscode.Range(node.line, 0, node.line, 1000),
              new vscode.Range(node.line, 0, node.line, 1000),
            ),
          );
        }

        if (node.children) {
          node.children.forEach(visit);
        }
      }

      ast.children.forEach(visit);
      return symbols;
    },
  };

  context.subscriptions.push(
    vscode.languages.registerDocumentSymbolProvider(LANGUAGE_ID, provider),
  );
}

module.exports = {
  registerDocumentSymbols,
};
