"use strict";

const vscode = require("vscode");
const { parse } = require("./parser");

/**
 * TableExplorer
 * -------------
 * A TreeView that shows all tables, functions, variables, imports,
 * and meta blocks in the current file. Clicking an item jumps to its
 * definition.
 */
class TableExplorerProvider {
  constructor(index) {
    this.index = index;
    this._onDidChange = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._onDidChange.event;
  }

  refresh() {
    this._onDidChange.fire(null);
  }

  getTreeItem(element) {
    return element;
  }

  getChildren(element) {
    if (!element) {
      // root: show categories
      return [
        this.makeCategory(
          "Tables",
          "tables",
          vscode.TreeItemCollapsibleState.Expanded,
        ),
        this.makeCategory(
          "Functions",
          "functions",
          vscode.TreeItemCollapsibleState.Collapsed,
        ),
        this.makeCategory(
          "Variables",
          "variables",
          vscode.TreeItemCollapsibleState.Collapsed,
        ),
        this.makeCategory(
          "Imports",
          "imports",
          vscode.TreeItemCollapsibleState.Collapsed,
        ),
        this.makeCategory(
          "Meta",
          "meta",
          vscode.TreeItemCollapsibleState.Collapsed,
        ),
      ];
    }

    const editor = vscode.window.activeTextEditor;
    if (!editor) return [];

    const doc = editor.document;
    if (doc.languageId !== "perchance") return [];

    const nodes = parse(doc.getText());

    if (element.contextValue === "category-tables") {
      return nodes
        .filter((n) => n.type === "table")
        .map((n) => {
          const item = new vscode.TreeItem(
            n.name,
            vscode.TreeItemCollapsibleState.Collapsed,
          );
          item.contextValue = "table";
          item.iconPath = new vscode.ThemeIcon("symbol-class");
          item.tooltip = `${n.items.length} items`;
          item.command = {
            command: "perchance.tableExplorer.goto",
            title: "Go to",
            arguments: [doc.uri, n.line - 1, n.name.length],
          };
          item.description = `${n.items.length} items`;
          return item;
        });
    }

    if (element.contextValue === "category-functions") {
      return nodes
        .filter((n) => n.type === "function")
        .map((n) => {
          const params = n.params
            .map((p) => (p.default ? `${p.name}=${p.default}` : p.name))
            .join(", ");
          const item = new vscode.TreeItem(
            `${n.name}(${params})`,
            vscode.TreeItemCollapsibleState.None,
          );
          item.contextValue = "function";
          item.iconPath = new vscode.ThemeIcon("symbol-function");
          item.command = {
            command: "perchance.tableExplorer.goto",
            title: "Go to",
            arguments: [doc.uri, n.line - 1, n.name.length],
          };
          return item;
        });
    }

    if (element.contextValue === "category-variables") {
      return nodes
        .filter((n) => n.type === "assignment")
        .map((n) => {
          const item = new vscode.TreeItem(
            `${n.name} = ${n.value}`,
            vscode.TreeItemCollapsibleState.None,
          );
          item.contextValue = "variable";
          item.iconPath = new vscode.ThemeIcon("symbol-variable");
          item.command = {
            command: "perchance.tableExplorer.goto",
            title: "Go to",
            arguments: [doc.uri, n.line - 1, n.name.length],
          };
          return item;
        });
    }

    if (element.contextValue === "category-imports") {
      return nodes
        .filter((n) => n.type === "import")
        .map((n) => {
          const item = new vscode.TreeItem(
            `${n.name} ← ${n.plugin}`,
            vscode.TreeItemCollapsibleState.None,
          );
          item.contextValue = "import";
          item.iconPath = new vscode.ThemeIcon("package");
          item.command = {
            command: "perchance.tableExplorer.goto",
            title: "Go to",
            arguments: [doc.uri, n.line - 1, n.name.length],
          };
          return item;
        });
    }

    if (element.contextValue === "category-meta") {
      const metaNode = nodes.find((n) => n.type === "meta");
      if (!metaNode) return [];
      return metaNode.subkeys.map((sk) => {
        const item = new vscode.TreeItem(
          `${sk.key}${sk.value ? " = " + sk.value : ""}`,
          vscode.TreeItemCollapsibleState.None,
        );
        item.contextValue = "meta-key";
        item.iconPath = new vscode.ThemeIcon("symbol-property");
        item.command = {
          command: "perchance.tableExplorer.goto",
          title: "Go to",
          arguments: [doc.uri, sk.line - 1, sk.key.length],
        };
        return item;
      });
    }

    // Table items (children of a table node)
    if (element.contextValue === "table") {
      // re-parse to get items for this table
      const nodes = parse(doc.getText());
      const tableName = element.label;
      const table = nodes.find(
        (n) => n.type === "table" && n.name === tableName,
      );
      if (!table) return [];
      return table.items.map((it, idx) => {
        let label = it.text.substring(0, 50);
        if (it.weight) {
          label +=
            it.weight.type === "static"
              ? ` ^${it.weight.value}`
              : ` ^[${it.weight.expr}]`;
        }
        const item = new vscode.TreeItem(
          label,
          vscode.TreeItemCollapsibleState.None,
        );
        item.contextValue = "table-item";
        item.iconPath = new vscode.ThemeIcon("list-item");
        item.command = {
          command: "perchance.tableExplorer.goto",
          title: "Go to",
          arguments: [doc.uri, it.line - 1, 0],
        };
        return item;
      });
    }

    return [];
  }

  makeCategory(label, key, state) {
    const item = new vscode.TreeItem(label, state);
    item.contextValue = `category-${key}`;
    item.iconPath = new vscode.ThemeIcon("folder");
    return item;
  }
}

module.exports = { TableExplorerProvider };
