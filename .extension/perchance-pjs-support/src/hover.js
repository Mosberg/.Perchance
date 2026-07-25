const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");
const { workspaceIndex } = require("./index");

function registerHover(context) {
  const provider = {
    provideHover(document, position) {
      if (document.languageId !== LANGUAGE_ID) return;

      const wordRange = document.getWordRangeAtPosition(position, /[\w$]+/);
      if (!wordRange) return;

      const word = document.getText(wordRange);
      const index = workspaceIndex.get(document.uri);
      const allTables = workspaceIndex.getAllTables();

      if (allTables.has(word)) {
        const tables = allTables.get(word);
        const md = new vscode.MarkdownString();
        md.appendCodeblock(word, "perchance");
        md.appendMarkdown(`\n\nDefined in ${tables.length} place(s).`);
        return new vscode.Hover(md, wordRange);
      }

      if (word === "$output" || word === "$meta") {
        const md = new vscode.MarkdownString();
        md.appendMarkdown(`**${word}** is a special Perchance block.`);
        return new vscode.Hover(md, wordRange);
      }

      return null;
    },
  };

  context.subscriptions.push(
    vscode.languages.registerHoverProvider(LANGUAGE_ID, provider),
  );
}

module.exports = {
  registerHover,
};
