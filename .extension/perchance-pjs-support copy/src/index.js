"use strict";

const path = require("path");
const vscode = require("vscode");
const { parse, BUILTINS } = require("./parser");

/**
 * WorkspaceIndex
 * --------------
 * Scans all .pjs/.perchance files in the workspace, builds a symbol
 * index for cross-file IntelliSense (definition, references, completion,
 * workspace symbols, dependency graph).
 *
 * Each symbol: { name, kind, file, line, references: string[] }
 * kind: 'table' | 'function' | 'variable' | 'import' | 'meta' | 'output'
 */
class WorkspaceIndex {
  constructor() {
    this.symbols = new Map(); // name -> SymbolInfo (last definition wins, but we store all)
    /** @type {Map<string, SymbolInfo[]>} name -> array of definitions across files */
    this.definitions = new Map();
    /** @type {Map<string, RefInfo[]>} file -> array of symbols defined in that file */
    this.fileSymbols = new Map();
    /** @type {Map<string, string[]>} file -> array of referenced names */
    this.fileReferences = new Map();
    this.maxFileSize = 500000;
    this.excludeGlobs = ["**/node_modules/**", "**/.git/**"];
    this._dirty = true;
  }

  setDirty() {
    this._dirty = true;
  }

  async rebuild(force = false) {
    if (!this._dirty && !force) return;
    this._dirty = false;
    this.definitions.clear();
    this.fileSymbols.clear();
    this.fileReferences.clear();

    const cfg = vscode.workspace.getConfiguration("perchance");
    if (!cfg.get("indexing.enabled", true)) return;
    this.maxFileSize = cfg.get("maxFileSize", 500000);
    this.excludeGlobs = cfg.get("indexing.exclude", [
      "**/node_modules/**",
      "**/.git/**",
    ]);

    const uris = await vscode.workspace.findFiles(
      "**/*.{pjs,perchance}",
      this.excludeGlobs.join(","),
    );
    for (const uri of uris) {
      try {
        await this.indexFile(uri);
      } catch (e) {
        // skip files that fail
      }
    }
  }

  async indexFile(uri) {
    const doc = await vscode.workspace.openTextDocument(uri);
    if (doc.byteLength > this.maxFileSize) return;
    this.parseDocument(doc.getText(), uri);
  }

  parseDocument(text, uri) {
    const nodes = parse(text);
    const symbols = [];
    const refs = [];

    for (const node of nodes) {
      switch (node.type) {
        case "table": {
          symbols.push({
            name: node.name,
            kind: "table",
            uri,
            line: node.line,
            node,
          });
          for (const item of node.items) {
            for (const r of item.references) refs.push(r);
          }
          break;
        }
        case "function":
          symbols.push({
            name: node.name,
            kind: "function",
            uri,
            line: node.line,
            node,
          });
          break;
        case "assignment":
          symbols.push({
            name: node.name,
            kind: "variable",
            uri,
            line: node.line,
            node,
          });
          break;
        case "import":
          symbols.push({
            name: node.name,
            kind: "import",
            uri,
            line: node.line,
            node,
          });
          refs.push(node.plugin);
          break;
        case "meta":
          symbols.push({
            name: "$meta",
            kind: "meta",
            uri,
            line: node.line,
            node,
          });
          break;
        case "output":
          symbols.push({
            name: "$output",
            kind: "output",
            uri,
            line: node.line,
            node,
          });
          // extract references from output expr
          {
            const { extractReferences } = require("./parser");
            for (const r of extractReferences(node.expr)) refs.push(r);
          }
          break;
        case "function":
          break;
      }
    }

    // store
    const uriStr = uri.toString();
    this.fileSymbols.set(uriStr, symbols);
    this.fileReferences.set(uriStr, refs);

    for (const s of symbols) {
      if (!this.definitions.has(s.name)) this.definitions.set(s.name, []);
      this.definitions.get(s.name).push(s);
    }
  }

  getDefinition(name) {
    return this.definitions.get(name) || [];
  }

  getAllDefinedNames() {
    return new Set(this.definitions.keys());
  }

  getReferencesTo(name) {
    const results = [];
    for (const [uri, refs] of this.fileReferences) {
      const lines = refs; // refs are names; but we need line numbers
      // Actually we stored names not locations. Let's store richer.
    }
    return results;
  }

  getSymbolsInFile(uri) {
    return this.fileSymbols.get(uri.toString()) || [];
  }

  getAllSymbols() {
    const all = [];
    for (const [name, defs] of this.definitions) {
      all.push(...defs);
    }
    return all;
  }

  // Build dependency edges: table -> [referenced table names]
  getDependencyGraph() {
    const edges = [];
    for (const [uri, symbols] of this.fileSymbols) {
      for (const s of symbols) {
        if (s.kind === "table" || s.kind === "output") {
          const node = s.node;
          let refs = [];
          if (s.kind === "table") {
            for (const item of node.items) refs.push(...item.references);
          } else {
            const { extractReferences } = require("./parser");
            refs = extractReferences(node.expr);
          }
          for (const r of refs) {
            if (this.definitions.has(r) || BUILTINS.includes(r)) continue;
            edges.push({
              from: s.name,
              to: r,
              fromFile: uri,
              fromLine: s.line,
            });
          }
        }
      }
    }
    return edges;
  }

  toSymbolInformation() {
    const result = [];
    const kindMap = {
      table: vscode.SymbolKind.Class,
      function: vscode.SymbolKind.Function,
      variable: vscode.SymbolKind.Variable,
      import: vscode.SymbolKind.Module,
      meta: vscode.SymbolKind.Property,
      output: vscode.SymbolKind.Field,
    };
    for (const [name, defs] of this.definitions) {
      for (const d of defs) {
        const range = new vscode.Range(d.line - 1, 0, d.line - 1, name.length);
        const loc = new vscode.Location(d.uri, range);
        result.push(
          new vscode.SymbolInformation(
            name,
            kindMap[d.kind] || vscode.SymbolKind.Variable,
            "",
            loc,
          ),
        );
      }
    }
    return result;
  }
}

module.exports = { WorkspaceIndex };
