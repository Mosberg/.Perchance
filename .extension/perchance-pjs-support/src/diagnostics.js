const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");
const { parseDocument } = require("./parser");

const collection = vscode.languages.createDiagnosticCollection("perchance");

function refreshDiagnostics(document) {
  if (document.languageId !== LANGUAGE_ID) return;

  const text = document.getText();
  const ast = parseDocument(text);
  const diagnostics = [];

  // Simple unmatched bracket check
  const stack = [];
  const lines = text.split(/\r?\n/);

  lines.forEach((line, lineNumber) => {
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === "[" || ch === "{" || ch === "(") {
        stack.push({ ch, line: lineNumber, col: i });
      } else if (ch === "]" || ch === "}" || ch === ")") {
        const last = stack.pop();
        if (!last) {
          diagnostics.push(
            new vscode.Diagnostic(
              new vscode.Range(lineNumber, i, lineNumber, i + 1),
              "Unmatched closing bracket",
              vscode.DiagnosticSeverity.Error,
            ),
          );
        }
      }
    }
  });

  if (stack.length > 0) {
    for (const unmatched of stack) {
      diagnostics.push(
        new vscode.Diagnostic(
          new vscode.Range(
            unmatched.line,
            unmatched.col,
            unmatched.line,
            unmatched.col + 1,
          ),
          "Unmatched opening bracket",
          vscode.DiagnosticSeverity.Error,
        ),
      );
    }
  }

  collection.set(document.uri, diagnostics);
}

function clearDiagnostics(document) {
  collection.delete(document.uri);
}

module.exports = {
  refreshDiagnostics,
  clearDiagnostics,
};
