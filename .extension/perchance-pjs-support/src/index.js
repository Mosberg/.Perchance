const { parseDocument, collectTables } = require("./parser");
const { LANGUAGE_ID } = require("./language");

const workspaceIndex = {
  documents: new Map(), // uri -> { ast, tables }
  clear() {
    this.documents.clear();
  },
  update(uri, text) {
    const ast = parseDocument(text);
    const tables = collectTables(ast);
    this.documents.set(uri.toString(), { ast, tables });
  },
  get(uri) {
    return this.documents.get(uri.toString()) || null;
  },
  getAllTables() {
    const result = new Map();
    for (const { tables } of this.documents.values()) {
      for (const [name, table] of tables.entries()) {
        if (!result.has(name)) {
          result.set(name, []);
        }
        result.get(name).push(table);
      }
    }
    return result;
  },
};

function indexDocument(document) {
  if (document.languageId !== LANGUAGE_ID) return;
  workspaceIndex.update(document.uri, document.getText());
}

module.exports = {
  workspaceIndex,
  indexDocument,
};
