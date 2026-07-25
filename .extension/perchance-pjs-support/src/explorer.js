const vscode = require("vscode");
const { workspaceIndex } = require("./index");
const { LANGUAGE_ID } = require("./language");

class TableTreeDataProvider {
  getTreeItem(element) {
    return element;
  }

  getChildren(element) {
    if (!element) {
      const items = [];
      const allTables = workspaceIndex.getAllTables();
      for (const name of allTables.keys()) {
        const item = new vscode.TreeItem(name);
        item.collapsibleState = vscode.TreeItemCollapsibleState.Collapsed;
        items.push(item);
      }
      return items;
    } else {
      const allTables = workspaceIndex.getAllTables();
      const tables = allTables.get(element.label) || [];
      return tables.map((t) => {
        const item = new vscode.TreeItem(`line ${t.line + 1}`);
        item.collapsibleState = vscode.TreeItemCollapsibleState.None;
        return item;
      });
    }
  }
}

function registerExplorer(context) {
  const provider = new TableTreeDataProvider();
  const tree = vscode.window.createTreeView("perchance.tableExplorer", {
    treeDataProvider: provider,
  });
  context.subscriptions.push(tree);
}

module.exports = {
  registerExplorer,
};
