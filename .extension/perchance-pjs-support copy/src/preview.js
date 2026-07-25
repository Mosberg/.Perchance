"use strict";

/**
 * Perchance Preview Generator
 * ---------------------------
 * A lightweight interpreter for a subset of Perchance syntax that can
 * run inside VSCode (no browser/perchance engine needed). Supports:
 *   - tables with weighted items
 *   - [table] references and [table.selectOne] etc.
 *   - inline {a|b|c} alternation with weights
 *   - numeric ranges {1-20}
 *   - simple [JS expression] blocks (evaluated with a safe-ish scope)
 *   - seeding via a custom PRNG
 *   - debug trace logging
 *
 * Limitations (documented to user): the real perchance engine has a much
 * richer JS sandbox, async, imports, and HTML rendering. This preview
 * is for quick local validation of generator logic. For full-fidelity
 * output, use the Perchance web editor.
 */

// ── Seeded PRNG (mulberry32) ─────────────────────────────────────
function createRng(seed) {
  let s = 0;
  if (typeof seed === "string") {
    for (let i = 0; i < seed.length; i++)
      s = (s * 31 + seed.charCodeAt(i)) >>> 0;
  } else if (typeof seed === "number") {
    s = seed >>> 0;
  }
  if (s === 0) s = 0x9e3779b9;
  return function () {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ── Interpreter ──────────────────────────────────────────────────
class Interpreter {
  constructor(nodes, opts = {}) {
    this.nodes = nodes;
    this.rng = opts.rng || createRng(opts.seed);
    this.seed = opts.seed;
    this.debug = opts.debug || false;
    this.trace = [];
    this.maxDepth = opts.maxDepth || 50;
    this._depth = 0;

    // Build lookup tables
    this.tables = new Map();
    this.vars = new Map();
    this.functions = new Map();
    this.imports = new Set();
    this.output = null;

    for (const node of nodes) {
      switch (node.type) {
        case "table":
          this.tables.set(node.name, node);
          break;
        case "assignment":
          this.vars.set(node.name, node.value);
          break;
        case "function":
          this.functions.set(node.name, node);
          break;
        case "import":
          this.imports.add(node.name);
          break;
        case "output":
          this.output = node.expr;
          break;
      }
    }
  }

  log(msg) {
    if (this.debug) this.trace.push(msg);
  }

  // Select from a table respecting weights
  selectFromTable(tableName) {
    if (this._depth > this.maxDepth) {
      this.log(`[depth limit reached at ${tableName}]`);
      return `[${tableName}]`;
    }
    this._depth++;
    try {
      const table = this.tables.get(tableName);
      if (!table) {
        this.log(`[undefined table: ${tableName}]`);
        return `[${tableName}]`;
      }

      const items = table.items;
      if (!items.length) return "";

      // compute weights
      const weights = items.map((it) => {
        if (!it.weight) return 1;
        if (it.weight.type === "static") return it.weight.value;
        if (it.weight.type === "dynamic") {
          try {
            const v = this.evalJsExpr(it.weight.expr);
            return typeof v === "number" ? v : v ? 1 : 0;
          } catch {
            return 0;
          }
        }
        return 1;
      });

      const total = weights.reduce((a, b) => a + b, 0);
      if (total <= 0) {
        // fallback: uniform
        const idx = Math.floor(this.rng() * items.length);
        return this.evalItem(items[idx]);
      }

      let r = this.rng() * total;
      let idx = 0;
      for (let i = 0; i < weights.length; i++) {
        r -= weights[i];
        if (r <= 0) {
          idx = i;
          break;
        }
        idx = i;
      }

      this.log(
        `selectFromTable(${tableName}) → item #${idx}: "${items[idx].text.substring(0, 40)}"`,
      );
      return this.evalItem(items[idx]);
    } finally {
      this._depth--;
    }
  }

  // Evaluate an item's text — expand [table], {a|b}, [js]
  evalItem(item) {
    return this.evalText(item.text);
  }

  evalText(text) {
    let result = "";
    let i = 0;
    while (i < text.length) {
      const c = text[i];

      // JS block [ ... ]
      if (c === "[") {
        const end = findMatching(text, i, "[", "]");
        if (end < 0) {
          result += c;
          i++;
          continue;
        }
        const expr = text.slice(i + 1, end);
        result += this.evalJsBlock(expr);
        i = end + 1;
        continue;
      }

      // Inline alternation { ... }
      if (c === "{") {
        const end = findMatching(text, i, "{", "}");
        if (end < 0) {
          result += c;
          i++;
          continue;
        }
        const alt = text.slice(i + 1, end);
        result += this.evalAlternation(alt);
        i = end + 1;
        continue;
      }

      // <br> → newline
      if (text.substr(i, 4).toLowerCase() === "<br>") {
        result += "\n";
        i += 4;
        continue;
      }

      result += c;
      i++;
    }
    return result;
  }

  // Evaluate inline alternation {opt1|opt2^3|opt3}
  evalAlternation(text) {
    // split on | but not || and not inside [..]
    const parts = [];
    let depth = 0;
    let cur = "";
    for (let j = 0; j < text.length; j++) {
      const c = text[j];
      if (c === "[") depth++;
      else if (c === "]") depth--;
      if (c === "|" && depth === 0) {
        parts.push(cur);
        cur = "";
      } else {
        cur += c;
      }
    }
    parts.push(cur);

    // parse weight from each part
    const weighted = parts.map((p) => {
      const caretIdx = findWeightCaretInline(p);
      if (caretIdx < 0) return { text: p, weight: 1 };
      const txt = p.slice(0, caretIdx);
      let w = p.slice(caretIdx + 1).trim();
      let weight = 1;
      if (/^\d+$/.test(w)) weight = parseInt(w, 10);
      else if (/^\[.*\]$/.test(w)) {
        try {
          weight = this.evalJsExpr(w.slice(1, -1));
          if (typeof weight !== "number") weight = weight ? 1 : 0;
        } catch {
          weight = 0;
        }
      }
      return { text: txt, weight };
    });

    const total = weighted.reduce((a, b) => a + b.weight, 0);
    if (total <= 0) return "";
    let r = this.rng() * total;
    let chosen = weighted[0];
    for (const w of weighted) {
      r -= w.weight;
      if (r <= 0) {
        chosen = w;
        break;
      }
    }
    return this.evalText(chosen.text);
  }

  // Evaluate a JS block expression
  evalJsBlock(expr) {
    this.log(`evalJsBlock: [${expr.substring(0, 60)}]`);
    // capture pattern: [x = table.selectOne, ""] then use x
    const captureMatch = expr.match(/^(\w+)\s*=\s*(.+?),\s*["']["']\s*$/);
    if (captureMatch) {
      const varName = captureMatch[1];
      const value = this.evalJsExpr(captureMatch[2]);
      this._scope = this._scope || {};
      this._scope[varName] = value;
      return "";
    }

    // Direct table reference: [tableName]
    const trim = expr.trim();
    if (/^\w+$/.test(trim) && this.tables.has(trim)) {
      return this.selectFromTable(trim);
    }

    // Table method: tableName.selectOne
    const selMatch = trim.match(/^(\w+)\.selectOne$/);
    if (selMatch && this.tables.has(selMatch[1])) {
      return this.selectFromTable(selMatch[1]);
    }

    // selectMany(n), selectUnique(n)
    const manyMatch = trim.match(/^(\w+)\.selectMany\((\d+)\)$/);
    if (manyMatch && this.tables.has(manyMatch[1])) {
      const n = parseInt(manyMatch[2], 10);
      const results = [];
      for (let i = 0; i < n; i++)
        results.push(this.selectFromTable(manyMatch[1]));
      return results.join(", ");
    }
    const uniqMatch = trim.match(/^(\w+)\.selectUnique\((\d+)\)$/);
    if (uniqMatch && this.tables.has(uniqMatch[1])) {
      const n = parseInt(uniqMatch[2], 10);
      const table = this.tables.get(uniqMatch[1]);
      const shuffled = [...table.items].sort(() => this.rng() - 0.5);
      const picked = shuffled.slice(0, Math.min(n, shuffled.length));
      return picked.map((it) => this.evalItem(it)).join(", ");
    }

    // getLength
    const lenMatch = trim.match(/^(\w+)\.getLength$/);
    if (lenMatch && this.tables.has(lenMatch[1])) {
      return String(this.tables.get(lenMatch[1]).items.length);
    }

    // joinItems
    const joinMatch = trim.match(/^(\w+)\.joinItems\((.*)\)$/);
    if (joinMatch && this.tables.has(joinMatch[1])) {
      const sep = this.evalJsExpr(joinMatch[2]);
      const items = this.tables
        .get(joinMatch[1])
        .items.map((it) => this.evalItem(it));
      return items.join(sep);
    }

    // Range: {1-20} already handled in evalText, but standalone
    const rangeMatch = trim.match(/^\{(\d+)-(\d+)\}$/);
    if (rangeMatch) {
      const lo = parseInt(rangeMatch[1], 10);
      const hi = parseInt(rangeMatch[2], 10);
      return String(lo + Math.floor(this.rng() * (hi - lo + 1)));
    }

    // Fallback: evaluate as JS expression
    return this.evalJsExpr(expr);
  }

  // Evaluate a JS expression in a limited scope
  evalJsExpr(expr) {
    if (!expr || !expr.trim()) return "";
    const scope = this._scope || {};
    // build a function with access to tables as objects
    const tableProxies = {};
    for (const [name, table] of this.tables) {
      const self = this;
      tableProxies[name] = {
        get selectOne() {
          return self.selectFromTable(name);
        },
        get getLength() {
          return table.items.length;
        },
        selectMany(n) {
          const r = [];
          for (let i = 0; i < n; i++) r.push(self.selectFromTable(name));
          return r;
        },
        selectUnique(n) {
          const shuffled = [...table.items].sort(() => self.rng() - 0.5);
          return shuffled.slice(0, n).map((it) => self.evalItem(it));
        },
        joinItems(sep) {
          return table.items.map((it) => self.evalItem(it)).join(sep);
        },
        get selectAll() {
          return table.items.map((it) => ({ evaluateItem: self.evalItem(it) }));
        },
      };
    }

    try {
      const keys = Object.keys(tableProxies)
        .concat(Object.keys(scope))
        .concat([
          "Math",
          "JSON",
          "String",
          "Array",
          "Object",
          "Number",
          "Boolean",
          "console",
          "root",
        ]);
      // root proxy
      const rootProxy = new Proxy(tableProxies, {
        get(t, prop) {
          return t[prop];
        },
        has() {
          return true;
        },
      });
      const values = keys.map((k) =>
        k === "root"
          ? rootProxy
          : scope[k] !== undefined
            ? scope[k]
            : tableProxies[k] || null,
      );
      const fn = new Function(...keys, `"use strict"; return (${expr});`);
      return fn(...values);
    } catch (e) {
      this.log(`JS eval error in "${expr}": ${e.message}`);
      return `[error: ${e.message}]`;
    }
  }

  // Generate final output
  generate() {
    if (this.output) {
      return this.evalText(this.output);
    }
    // if there's a top-level $output reference, use it
    // Otherwise, find the last table and generate from it
    const tables = [...this.tables.values()];
    if (tables.length) {
      return this.selectFromTable(tables[tables.length - 1].name);
    }
    return "(no output)";
  }

  generateN(n) {
    const results = [];
    for (let i = 0; i < n; i++) {
      this._depth = 0;
      this._scope = undefined;
      results.push(this.generate());
    }
    return results;
  }
}

function findMatching(text, start, open, close) {
  let depth = 0;
  let inStr = null;
  for (let i = start; i < text.length; i++) {
    const c = text[i];
    if (inStr) {
      if (c === "\\") i++;
      else if (c === inStr) inStr = null;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") inStr = c;
    else if (c === open) depth++;
    else if (c === close) {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

function findWeightCaretInline(s) {
  let depth = 0;
  let inStr = null;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (inStr) {
      if (c === "\\") i++;
      else if (c === inStr) inStr = null;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") inStr = c;
    if (c === "[") depth++;
    else if (c === "]") depth--;
    else if (c === "^" && depth === 0) return i;
  }
  return -1;
}

function runPreview(text, opts = {}) {
  const { parse } = require("./parser");
  const nodes = parse(text);
  const interp = new Interpreter(nodes, opts);
  const output = interp.generate();
  return { output, trace: interp.trace };
}

function runPreviewN(text, n, opts = {}) {
  const { parse } = require("./parser");
  const nodes = parse(text);
  const results = [];
  for (let i = 0; i < n; i++) {
    const interp = new Interpreter(nodes, {
      ...opts,
      seed: opts.seed ? opts.seed + "-" + i : undefined,
    });
    interp._depth = 0;
    results.push(interp.generate());
  }
  return results;
}

module.exports = { Interpreter, runPreview, runPreviewN, createRng };
