const { parseDocument, collectTables } = require("./parser");

function buildDependencyGraph(text) {
  const ast = parseDocument(text);
  const tables = collectTables(ast);
  const nodes = [];
  const edges = [];

  for (const [name, table] of tables.entries()) {
    nodes.push({ id: name });
    const regex = /\[([A-Za-z_][\w$]*)\]/g;
    table.children.forEach((item) => {
      if (item.type !== "item") return;
      let match;
      while ((match = regex.exec(item.text)) !== null) {
        const target = match[1];
        edges.push({ from: name, to: target });
      }
    });
  }

  return { nodes, edges };
}

module.exports = {
  buildDependencyGraph,
};
