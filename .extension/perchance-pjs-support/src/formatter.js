const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");

function registerFormatter(context) {
  const provider = {
    provideDocumentFormattingEdits(document) {
      if (document.languageId !== LANGUAGE_ID) return [];

      const config = vscode.workspace.getConfiguration("perchance.format");
      const indentSize = config.get("indentSize", 2);
      const indent = " ".repeat(indentSize);

      const lines = document.getText().split(/\r?\n/);
      const edits = [];
      let currentIndent = 0;

      lines.forEach((line, lineNumber) => {
        const trimmed = line.trim();
        if (!trimmed) return;

        // crude heuristic: table/function/block lines reset indent
        if (
          /^[A-Za-z_][\w$]*\s*(\([^)]*\)\s*=>)?\s*$/.test(trimmed) ||
          trimmed.startsWith("$")
        ) {
          currentIndent = 0;
        }

        const newLine = indent.repeat(currentIndent) + trimmed;
        if (newLine !== line) {
          edits.push(
            vscode.TextEdit.replace(
              new vscode.Range(lineNumber, 0, lineNumber, line.length),
              newLine,
            ),
          );
        }

        // increase indent after table/function/block header
        if (
          /^[A-Za-z_][\w$]*\s*(\([^)]*\)\s*=>)?\s*$/.test(trimmed) ||
          trimmed.startsWith("$")
        ) {
          currentIndent = 1;
        }
      });

      return edits;
    },
  };

  context.subscriptions.push(
    vscode.languages.registerDocumentFormattingEditProvider(
      LANGUAGE_ID,
      provider,
    ),
  );
}

module.exports = {
  registerFormatter,
};
