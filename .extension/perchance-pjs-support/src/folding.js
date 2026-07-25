const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");
const { parseDocument } = require("./parser");

function registerFolding(context) {
  const provider = {
    provideFoldingRanges(document) {
      if (document.languageId !== LANGUAGE_ID) return [];

      const ast = parseDocument(document.getText());
      const ranges = [];

      function visit(node) {
        if (node.children && node.children.length > 0) {
          const start = node.line;
          const end = node.children[node.children.length - 1].line;
          if (end > start) {
            ranges.push(
              new vscode.FoldingRange(
                start,
                end,
                vscode.FoldingRangeKind.Region,
              ),
            );
          }
          node.children.forEach(visit);
        }
      }

      ast.children.forEach(visit);
      return ranges;
    },
  };

  context.subscriptions.push(
    vscode.languages.registerFoldingRangeProvider(LANGUAGE_ID, provider),
  );
}

module.exports = {
  registerFolding,
};
