"use strict";

const vscode = require("vscode");
const { parse, BUILTINS, extractReferences } = require("./parser");

/**
 * GraphView
 * --------
 * Renders an interactive dependency graph of table → table references
 * in a webview. Uses a simple force-directed or hierarchical layout
 * drawn on a <canvas>. Supports zoom/pan, node hover, and clicking a
 * node to jump to its definition.
 */
class GraphView {
  constructor(context, index) {
    this.context = context;
    this.index = index;
    this.view = null;
  }

  async show(docUri) {
    if (this.view) {
      this.view.reveal(vscode.ViewColumn.Two, true);
      this.refresh(docUri);
      return;
    }
    this.view = vscode.window.createWebviewPanel(
      "perchance.graph",
      "Perchance Dependency Graph",
      vscode.ViewColumn.Two,
      {
        enableScripts: true,
        retainContextWhenHidden: false,
        localResourceRoots: [],
      },
    );
    this.view.onDidDispose(() => {
      this.view = null;
    });
    this.view.webview.onDidReceiveMessage((msg) => this.onMessage(msg));
    this.view.iconPath = new vscode.ThemeIcon("graph");
    await this.refresh(docUri);
  }

  async refresh(docUri) {
    if (!this.view) return;
    await this.index.rebuild();
    const layout = vscode.workspace
      .getConfiguration("perchance")
      .get("graph.layout", "hierarchical");

    // Collect nodes and edges from the current doc + workspace
    let nodes = [];
    let edges = [];

    if (docUri) {
      const doc = await vscode.workspace.openTextDocument(docUri);
      const parsed = parse(doc.getText());
      const tableNames = new Set(
        parsed.filter((n) => n.type === "table").map((n) => n.name),
      );
      for (const n of parsed) {
        if (n.type === "table") {
          nodes.push({
            id: n.name,
            label: n.name,
            line: n.line,
            file: docUri.toString(),
          });
          for (const item of n.items) {
            for (const ref of item.references) {
              if (!BUILTINS.includes(ref) && ref !== "root" && ref !== "this") {
                edges.push({ from: n.name, to: ref });
              }
            }
          }
        }
      }
    }

    // deduplicate nodes
    const nodeMap = new Map();
    for (const n of nodes) nodeMap.set(n.id, n);
    // add target nodes that exist as edges but maybe weren't added
    for (const e of edges) {
      if (!nodeMap.has(e.to)) {
        // check if it's defined somewhere
        const defs = this.index.getDefinition(e.to);
        if (defs.length) {
          nodeMap.set(e.to, {
            id: e.to,
            label: e.to,
            line: defs[0].line,
            file: defs[0].uri.toString(),
          });
        } else {
          nodeMap.set(e.to, {
            id: e.to,
            label: e.to + " ?",
            line: 0,
            file: "",
            undefined: true,
          });
        }
      }
    }
    // deduplicate edges
    const edgeSet = new Set();
    edges = edges.filter((e) => {
      const k = `${e.from}->${e.to}`;
      if (edgeSet.has(k)) return false;
      edgeSet.add(k);
      return true;
    });

    const html = this.getHtml([...nodeMap.values()], edges, layout);
    this.view.webview.html = html;
  }

  onMessage(msg) {
    if (msg.type === "goto") {
      const name = msg.name;
      const defs = this.index.getDefinition(name);
      if (defs.length) {
        const def = defs[0];
        const line = def.line - 1;
        vscode.window.showTextDocument(def.uri, {
          selection: new vscode.Range(line, 0, line, name.length),
        });
      }
    }
  }

  getHtml(nodes, edges, layout) {
    const data = JSON.stringify({ nodes, edges, layout });
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Perchance Dependency Graph</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 100%; height: 100%; overflow: hidden; background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); }
  #canvas { display: block; width: 100%; height: 100%; cursor: grab; }
  #canvas:active { cursor: grabbing; }
  #tooltip { position: fixed; padding: 4px 8px; background: var(--vscode-editorHoverWidget-background); border: 1px solid var(--vscode-editorHoverWidget-border); border-radius: 3px; font-size: 12px; pointer-events: none; display: none; z-index: 10; }
  #info { position: fixed; top: 8px; left: 8px; padding: 6px 10px; background: var(--vscode-editorWidget-background); border: 1px solid var(--vscode-editorWidget-border); border-radius: 4px; font-size: 12px; opacity: 0.85; }
  #legend { position: fixed; bottom: 8px; left: 8px; padding: 6px 10px; background: var(--vscode-editorWidget-background); border: 1px solid var(--vscode-editorWidget-border); border-radius: 4px; font-size: 12px; line-height: 1.6; }
  .legend-item { display: flex; align-items: center; gap: 6px; }
  .legend-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
</style>
</head>
<body>
<canvas id="canvas"></canvas>
<div id="tooltip"></div>
<div id="info">Nodes: ${nodes.length} · Edges: ${edges.length} · Scroll to zoom, drag to pan, click a node to open</div>
<div id="legend">
  <div class="legend-item"><span class="legend-dot" style="background:var(--vscode-symbolIcon-class-foreground,#4ec9b0)"></span> Table</div>
  <div class="legend-item"><span class="legend-dot" style="background:var(--vscode-symbolIcon-variable-foreground,#9cdcfe)"></span> Variable</div>
  <div class="legend-item"><span class="legend-dot" style="background:var(--vscode-errorForeground,#f48771)"></span> Undefined</div>
</div>
<script>
  const vscode = acquireVsCodeApi();
  const data = ${data};
  const canvas = document.getElementById('canvas');
  const ctx = canvas.getContext('2d');
  const tooltip = document.getElementById('tooltip');
  let dpr = window.devicePixelRatio || 1;
  let pan = { x: 0, y: 0 };
  let scale = 1;
  let mouseX = 0, mouseY = 0;
  let dragging = false;
  let hoveredNode = null;
  let nodePositions = [];

  function resize() {
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    canvas.style.width = window.innerWidth + 'px';
    canvas.style.height = window.innerHeight + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  // ── Layout ─────────────────────────────────
  function layout() {
    const W = window.innerWidth, H = window.innerHeight;
    if (data.layout === 'radial') layoutRadial(W, H);
    else if (data.layout === 'force-directed') layoutForce(W, H);
    else layoutHierarchical(W, H);
  }

  function layoutHierarchical(W, H) {
    // Group by depth (longest path from a root = a node with no incoming edges)
    const inDeg = new Map(data.nodes.map(n => [n.id, 0]));
    for (const e of data.edges) inDeg.set(e.to, (inDeg.get(e.to) || 0) + 1);
    const roots = data.nodes.filter(n => (inDeg.get(n.id) || 0) === 0);
    // BFS layers
    const level = new Map();
    roots.forEach(r => level.set(r.id, 0));
    let changed = true;
    while (changed) {
      changed = false;
      for (const e of data.edges) {
        if (level.has(e.from) && !level.has(e.to)) { level.set(e.to, level.get(e.from) + 1); changed = true; }
        if (level.has(e.to) && !level.has(e.from)) { level.set(e.from, level.get(e.to) + 1); changed = true; }
      }
    }
    // assign levels to unvisited
    data.nodes.forEach((n, i) => { if (!level.has(n.id)) level.set(n.id, 0); });
    const maxLevel = Math.max(...level.values(), 0);
    const byLevel = new Map();
    data.nodes.forEach(n => {
      const l = level.get(n.id) || 0;
      if (!byLevel.has(l)) byLevel.set(l, []);
      byLevel.get(l).push(n);
    });
    nodePositions = data.nodes.map(n => {
      const l = level.get(n.id) || 0;
      const siblings = byLevel.get(l) || [n];
      const idx = siblings.indexOf(n);
      const layerH = H / (maxLevel + 2);
      const colW = W / (siblings.length + 1);
      return { id: n.id, label: n.label, x: colW * (idx + 1), y: layerH * (l + 1), node: n };
    });
  }

  function layoutRadial(W, H) {
    const cx = W / 2, cy = H / 2;
    const radius = Math.min(W, H) * 0.35;
    data.nodes.forEach((n, i) => {
      const angle = (i / data.nodes.length) * Math.PI * 2;
      nodePositions.push({ id: n.id, label: n.label, x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius, node: n });
    });
  }

  function layoutForce(W, H) {
    // simple force-directed: initialize random, iterate
    nodePositions = data.nodes.map(n => ({ id: n.id, label: n.label, x: Math.random() * W, y: Math.random() * H, vx: 0, vy: 0, node: n }));
    const k = 80; // ideal distance
    for (let iter = 0; iter < 300; iter++) {
      // repulsion
      for (let i = 0; i < nodePositions.length; i++) {
        for (let j = i + 1; j < nodePositions.length; j++) {
          let dx = nodePositions[i].x - nodePositions[j].x;
          let dy = nodePositions[i].y - nodePositions[j].y;
          let d = Math.sqrt(dx*dx + dy*dy) || 1;
          let f = (k * k) / (d * d);
          nodePositions[i].vx += (dx / d) * f * 0.1;
          nodePositions[i].vy += (dy / d) * f * 0.1;
          nodePositions[j].vx -= (dx / d) * f * 0.1;
          nodePositions[j].vy -= (dy / d) * f * 0.1;
        }
      }
      // attraction (edges)
      for (const e of data.edges) {
        const a = nodePositions.find(p => p.id === e.from);
        const b = nodePositions.find(p => p.id === e.to);
        if (!a || !b) continue;
        let dx = b.x - a.x, dy = b.y - a.y;
        let d = Math.sqrt(dx*dx + dy*dy) || 1;
        let f = (d * d) / k * 0.005;
        a.vx += (dx / d) * f; a.vy += (dy / d) * f;
        b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
      }
      // apply velocity with damping and keep in bounds
      for (const p of nodePositions) {
        p.x += p.vx * 0.5; p.y += p.vy * 0.5;
        p.vx *= 0.9; p.vy *= 0.9;
        p.x = Math.max(40, Math.min(W - 40, p.x));
        p.y = Math.max(40, Math.min(H - 40, p.y));
      }
    }
  }

  // ── Draw ──────────────────────────────────
  function draw() {
    ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
    ctx.save();
    ctx.translate(pan.x, pan.y);
    ctx.scale(scale, scale);

    // edges
    ctx.strokeStyle = 'rgba(128,128,128,0.35)';
    ctx.lineWidth = 1;
    for (const e of data.edges) {
      const a = nodePositions.find(p => p.id === e.from);
      const b = nodePositions.find(p => p.id === e.to);
      if (!a || !b) continue;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      // arrowhead
      const angle = Math.atan2(b.y - a.y, b.x - a.x);
      ctx.beginPath();
      ctx.moveTo(b.x, b.y);
      ctx.lineTo(b.x - 8 * Math.cos(angle - 0.3), b.y - 8 * Math.sin(angle - 0.3));
      ctx.lineTo(b.x - 8 * Math.cos(angle + 0.3), b.y - 8 * Math.sin(angle + 0.3));
      ctx.closePath();
      ctx.fillStyle = 'rgba(128,128,128,0.5)';
      ctx.fill();
    }

    // nodes
    for (const p of nodePositions) {
      const isUndef = p.node && p.node.undefined;
      const isVar = p.node && false; // could detect variable vs table
      const color = isUndef ? 'var(--vscode-errorForeground,#f48771)'
        : 'var(--vscode-symbolIcon-class-foreground,#4ec9b0)';
      // resolve CSS var on canvas (fall back to hex)
      const fillColor = isUndef ? '#f48771' : '#4ec9b0';
      const r = p === hoveredNode ? 10 : 7;
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fillStyle = fillColor;
      ctx.fill();
      ctx.strokeStyle = p === hoveredNode ? '#fff' : 'rgba(0,0,0,0.3)';
      ctx.lineWidth = p === hoveredNode ? 2 : 1;
      ctx.stroke();
      // label
      ctx.fillStyle = 'var(--vscode-editor-foreground,#ddd)';
      ctx.fillStyle = '#ddd';
      ctx.font = '12px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(p.label, p.x, p.y + 20);
    }
    ctx.restore();
  }

  // ── Interaction ───────────────────────────
  canvas.addEventListener('mousedown', e => { dragging = true; canvas._drag = { x: e.clientX - pan.x, y: e.clientY - pan.y }; });
  canvas.addEventListener('mouseup', () => dragging = false);
  canvas.addEventListener('mousemove', e => {
    mouseX = e.clientX; mouseY = e.clientY;
    if (dragging) {
      pan.x = e.clientX - canvas._drag.x;
      pan.y = e.clientY - canvas._drag.y;
      draw();
      return;
    }
    // hover
    const wx = (mouseX - pan.x) / scale;
    const wy = (mouseY - pan.y) / scale;
    let found = null;
    for (const p of nodePositions) {
      const dx = p.x - wx, dy = p.y - wy;
      if (dx*dx + dy*dy < 144) { found = p; break; }
    }
    if (found !== hoveredNode) {
      hoveredNode = found;
      draw();
    }
    if (found) {
      tooltip.style.display = 'block';
      tooltip.style.left = (mouseX + 12) + 'px';
      tooltip.style.top = (mouseY + 12) + 'px';
      tooltip.textContent = found.label + (found.node && found.node.line ? ' (line ' + found.node.line + ')' : '');
      canvas.style.cursor = 'pointer';
    } else {
      tooltip.style.display = 'none';
      canvas.style.cursor = dragging ? 'grabbing' : 'grab';
    }
  });
  canvas.addEventListener('click', e => {
    if (hoveredNode) {
      vscode.postMessage({ type: 'goto', name: hoveredNode.id });
    }
  });
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    scale = Math.max(0.2, Math.min(5, scale * delta));
    draw();
  }, { passive: false });

  window.addEventListener('resize', resize);
  layout();
  resize();
  // re-layout on window resize if force-directed (already computed)
</script>
</body>
</html>`;
  }
}

module.exports = { GraphView };
