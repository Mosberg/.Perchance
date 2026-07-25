/**
 * Very lightweight Perchance (.pjs) parser.
 * Builds a tree of blocks based on indentation and simple patterns.
 */

function parseDocument(text) {
  const lines = text.split(/\r?\n/);
  const root = { type: "root", children: [] };
  const stack = [{ indent: 0, node: root }];

  for (let lineNumber = 0; lineNumber < lines.length; lineNumber++) {
    const raw = lines[lineNumber];
    const indent = raw.match(/^\s*/)[0].length;
    const line = raw.trim();

    if (!line || line.startsWith("//")) {
      continue;
    }

    while (stack.length > 1 && indent < stack[stack.length - 1].indent) {
      stack.pop();
    }

    const parent = stack[stack.length - 1].node;
    const node = parseLine(line, lineNumber, indent);
    parent.children.push(node);

    if (
      node.type === "table" ||
      node.type === "function" ||
      node.type === "block"
    ) {
      stack.push({ indent: indent + 1, node });
    }
  }

  return root;
}

function parseLine(line, lineNumber, indent) {
  // function: name(args) =>
  const fnMatch = line.match(/^([A-Za-z_][\w$]*)\s*\(([^)]*)\)\s*=>\s*$/);
  if (fnMatch) {
    return {
      type: "function",
      name: fnMatch[1],
      params: fnMatch[2].trim(),
      line: lineNumber,
      indent,
      children: [],
    };
  }

  // special blocks
  if (line.startsWith("$meta")) {
    return {
      type: "block",
      name: "$meta",
      line: lineNumber,
      indent,
      children: [],
    };
  }
  if (line.startsWith("$output")) {
    return {
      type: "output",
      text: line,
      line: lineNumber,
      indent,
    };
  }

  // import: name = {import:...}
  const importMatch = line.match(
    /^([A-Za-z_][\w$]*)\s*=\s*\{import:([^}]+)\}\s*$/,
  );
  if (importMatch) {
    return {
      type: "import",
      name: importMatch[1],
      target: importMatch[2].trim(),
      line: lineNumber,
      indent,
    };
  }

  // assignment: name = value
  const assignMatch = line.match(/^([A-Za-z_][\w$]*)\s*=\s*(.+)$/);
  if (assignMatch) {
    return {
      type: "assignment",
      name: assignMatch[1],
      value: assignMatch[2],
      line: lineNumber,
      indent,
    };
  }

  // table header: bare identifier
  const tableMatch = line.match(/^([A-Za-z_][\w$]*)$/);
  if (tableMatch) {
    return {
      type: "table",
      name: tableMatch[1],
      line: lineNumber,
      indent,
      children: [],
    };
  }

  // list item (with optional weight)
  const itemMatch = line.match(/^(.+?)(\^[^\s]+)?$/);
  return {
    type: "item",
    text: itemMatch[1].trim(),
    weight: itemMatch[2] || null,
    line: lineNumber,
    indent,
  };
}

function collectTables(ast) {
  const tables = new Map();

  function visit(node, parentTable) {
    if (node.type === "table") {
      tables.set(node.name, node);
      parentTable = node;
    }
    if (node.children) {
      for (const child of node.children) {
        visit(child, parentTable);
      }
    }
  }

  visit(ast, null);
  return tables;
}

module.exports = {
  parseDocument,
  collectTables,
};
