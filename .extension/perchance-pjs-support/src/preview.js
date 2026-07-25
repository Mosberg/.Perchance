const vscode = require("vscode");
const { createInterpreter } = require("./interpreter");
const { LANGUAGE_ID } = require("./language");

async function showPreview(document, runs, seed) {
  const text = document.getText();
  const interpreter = createInterpreter(text, seed);
  const outputs = [];

  for (let i = 0; i < runs; i++) {
    outputs.push(interpreter.getOutput());
  }

  const panel = vscode.window.createWebviewPanel(
    "perchancePreview",
    "Perchance Preview",
    vscode.ViewColumn.Beside,
    {},
  );

  panel.webview.html = renderHtml(outputs, seed);
}

function renderHtml(outputs, seed) {
  const body = outputs
    .map(
      (o, i) =>
        `<div class="run"><span class="idx">#${i + 1}</span><pre>${escapeHtml(o)}</pre></div>`,
    )
    .join("");

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
body { font-family: system-ui, sans-serif; padding: 12px; }
.run { margin-bottom: 8px; }
.idx { font-weight: bold; margin-right: 8px; color: #888; }
pre { display: inline-block; margin: 0; white-space: pre-wrap; }
.seed { margin-bottom: 12px; color: #666; }
</style>
</head>
<body>
<div class="seed">Seed: ${seed || "<random>"}</div>
${body}
</body>
</html>`;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function registerPreviewCommands(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("perchance.preview", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.document.languageId !== LANGUAGE_ID) return;
      const config = vscode.workspace.getConfiguration("perchance.preview");
      const runs = config.get("defaultRuns", 5);
      const seed = config.get("defaultSeed", "");
      await showPreview(editor.document, runs, seed);
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("perchance.previewMulti", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.document.languageId !== LANGUAGE_ID) return;
      const runs = await vscode.window.showInputBox({
        prompt: "Number of runs",
        value: "10",
      });
      if (!runs) return;
      await showPreview(editor.document, parseInt(runs, 10) || 10, "");
    }),
  );
}

module.exports = {
  registerPreviewCommands,
};
