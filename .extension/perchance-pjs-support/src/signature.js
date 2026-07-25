const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");

function registerSignatureHelp(context) {
  const provider = {
    provideSignatureHelp(document, position) {
      if (document.languageId !== LANGUAGE_ID) return null;

      const line = document.lineAt(position.line).text;
      const before = line.slice(0, position.character);
      const fnMatch = before.match(/([A-Za-z_][\w$]*)\s*\(([^)]*)$/);
      if (!fnMatch) return null;

      const fnName = fnMatch[1];

      const sig = new vscode.SignatureInformation(
        `${fnName}(...)`,
        "Perchance function call",
      );
      sig.parameters = [new vscode.ParameterInformation("...")];

      const help = new vscode.SignatureHelp();
      help.signatures = [sig];
      help.activeSignature = 0;
      help.activeParameter = 0;
      return help;
    },
  };

  context.subscriptions.push(
    vscode.languages.registerSignatureHelpProvider(
      LANGUAGE_ID,
      provider,
      "(",
      ",",
    ),
  );
}

module.exports = {
  registerSignatureHelp,
};
