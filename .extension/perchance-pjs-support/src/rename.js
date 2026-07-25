const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");

function registerRename(context) {
  const provider = {
    provideRenameEdits(document, position, newName) {
      if (document.languageId !== LANGUAGE_ID) {
        return Promise.reject("Not a Perchance document");
      }

      const wordRange = document.getWordRangeAtPosition(position, /[\w$]+/);
      if (!wordRange) {
        return Promise.reject("No symbol at position");
      }

      const oldName = document.getText(wordRange);
      const text = document.getText();
      const regex = new RegExp(`\\b${oldName}\\b`, "g");
      const lines = text.split(/\r?\n/);

      const workspaceEdit = new vscode.WorkspaceEdit();

      lines.forEach((line, lineNumber) => {
        let match;
        while ((match = regex.exec(line)) !== null) {
          const start = match.index;
          const end = start + oldName.length;
          workspaceEdit.replace(
            document.uri,
            new vscode.Range(lineNumber, start, lineNumber, end),
            newName,
          );
        }
      });

      return workspaceEdit;
    },
    prepareRename(document, position) {
      if (document.languageId !== LANGUAGE_ID) return null;
      const wordRange = document.getWordRangeAtPosition(position, /[\w$]+/);
      if (!wordRange) return null;
      return wordRange;
    },
  };

  context.subscriptions.push(
    vscode.languages.registerRenameProvider(LANGUAGE_ID, provider),
  );
}

module.exports = {
  registerRename,
};
