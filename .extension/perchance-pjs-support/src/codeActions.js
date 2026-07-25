const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");

function registerCodeActions(context) {
  const provider = {
    provideCodeActions(document, range, contextInfo) {
      if (document.languageId !== LANGUAGE_ID) return [];

      const actions = [];

      for (const diag of contextInfo.diagnostics) {
        if (diag.message.includes("Unmatched")) {
          const fix = new vscode.CodeAction(
            "Perchance: Comment out problematic line",
            vscode.CodeActionKind.QuickFix,
          );
          fix.edit = new vscode.WorkspaceEdit();
          const line = document.lineAt(diag.range.start.line);
          fix.edit.replace(
            document.uri,
            new vscode.Range(
              line.lineNumber,
              0,
              line.lineNumber,
              line.text.length,
            ),
            "// " + line.text,
          );
          fix.diagnostics = [diag];
          actions.push(fix);
        }
      }

      return actions;
    },
  };

  context.subscriptions.push(
    vscode.languages.registerCodeActionsProvider(LANGUAGE_ID, provider, {
      providedCodeActionKinds: [vscode.CodeActionKind.QuickFix],
    }),
  );
}

module.exports = {
  registerCodeActions,
};
