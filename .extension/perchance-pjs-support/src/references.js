const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");
const { workspaceIndex } = require("./index");

function registerReferences(context) {
  const provider = {
    provideReferences(document, position, contextRef) {
      if (document.languageId !== LANGUAGE_ID) return;

      const wordRange = document.getWordRangeAtPosition(position, /[\w$]+/);
      if (!wordRange) return;

      const word = document.getText(wordRange);
      const text = document.getText();
      const locations = [];

      const regex = new RegExp(`\\b${word}\\b`, "g");
      const lines = text.split(/\r?\n/);

      lines.forEach((line, lineNumber) => {
        let match;
        while ((match = regex.exec(line)) !== null) {
          const start = match.index;
          const end = start + word.length;
          locations.push(
            new vscode.Location(
              document.uri,
              new vscode.Range(lineNumber, start, lineNumber, end),
            ),
          );
        }
      });

      return locations;
    },
  };

  context.subscriptions.push(
    vscode.languages.registerReferenceProvider(LANGUAGE_ID, provider),
  );
}

module.exports = {
  registerReferences,
};
