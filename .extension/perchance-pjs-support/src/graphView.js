const vscode = require("vscode");
const { LANGUAGE_ID } = require("./language");
const { buildDependencyGraph } = require("./graph");

function registerGraphCommand(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("perchance.showGraph", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.document.languageId !== LANGUAGE_ID) return;

      const graph = buildDependencyGraph(editor.document.getText());
      const panel = vscode.window.createWebviewPanel(
        "perchanceGraph",
        "Perchance Table Graph",
        vscode.ViewColumn.Beside,
        {},
      );

      panel.webview.html = renderGraphHtml(graph);
    }),
  );
}

function renderGraphHtml(graph) {
  const nodesJson = JSON.stringify(graph.nodes);
  const edgesJson = JSON.stringify(graph.edges);

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
body { font-family: system-ui, sans-serif; margin: 0; padding: 0; }
#graph { width: 100vw; height: 100vh; }
.node { padding: 4px 8px; border-radius: 4px; background: #2d2d30; color: #fff; display: inline-block; margin: 4px; }
.edge { color: #888; font-size: 12px; }
</style>
</head>
<body>
<div id="graph"></div>
<script>
const nodes = ${nodesJson};
const edges = ${edgesJson};
const container = document.getElementById('graph');

nodes.forEach(n => {
  const div = document.createElement('div');
  div.className = 'node';
  div.textContent = n.id;
  container.appendChild(div);
});

const edgesDiv = document.createElement('div');
edgesDiv.style.marginTop = '12px';
edges.forEach(e => {
  const span = document.createElement('div');
  span.className = 'edge';
  span.textContent = e.from + ' -> ' + e.to;
  edgesDiv.appendChild(span);
});
container.appendChild(edgesDiv);
</script>
</body>
</html>`;
}

module.exports = {
  registerGraphCommand,
};
