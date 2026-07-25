/**
 * Extremely minimal Perchance interpreter for preview:
 * - picks a random item from a named table
 * - resolves $output if present
 */

const { parseDocument, collectTables } = require("./parser");

function createInterpreter(text, seed) {
  const ast = parseDocument(text);
  const tables = collectTables(ast);
  let rng = Math.random;
  if (seed && seed.length) {
    let s = 0;
    for (const ch of seed) s = (s * 31 + ch.charCodeAt(0)) >>> 0;
    rng = () => {
      s ^= s << 13;
      s ^= s >>> 17;
      s ^= s << 5;
      return (s >>> 0) / 0xffffffff;
    };
  }

  function selectOne(tableName) {
    const table = tables.get(tableName);
    if (!table || !table.children || !table.children.length) return "";
    const items = table.children.filter((c) => c.type === "item");
    if (!items.length) return "";
    const idx = Math.floor(rng() * items.length);
    return items[idx].text;
  }

  function getOutput() {
    // naive: look for $output assignment
    for (const node of ast.children) {
      if (node.type === "output") {
        const match = node.text.match(/\[(.+?)\]/);
        if (match) {
          return selectOne(match[1]);
        }
      }
    }
    // fallback: first table
    const firstTable = ast.children.find((n) => n.type === "table");
    if (firstTable) return selectOne(firstTable.name);
    return "";
  }

  return {
    selectOne,
    getOutput,
  };
}

module.exports = {
  createInterpreter,
};
