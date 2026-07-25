# VSCode Perchance (.pjs) Language Support Extension

A full-feature list for a **VSCode Perchance (.pjs) Language Support Extension** needs to cover _editor UX_, _syntax intelligence_, _runtime tooling_, _project‑level automation_, and _Perchance‑specific ergonomics_. Below is a structured, comprehensive feature set you can use as a blueprint for your extension.

---

## Core Language Features

- **Syntax Highlighting** — Full TextMate grammar for `.pjs`, `.perchance`, embedded JS, tables, macros, weighted lists, generators, and HTML‑in‑Perchance.
- **Semantic Tokens** — Highlight variables, macros, table names, generator blocks, comments, and control structures with semantic meaning.
- **Language Configuration** — Comment toggling, bracket matching, auto‑closing, auto‑surround, indentation rules, folding markers.

---

## Completion & IntelliSense

- **Completion Items** — Variables, macros, table names, generator names, built‑in functions, Perchance keywords.
- **Snippet Completions** — Tables, weighted lists, variables, macros, generators, conditionals, loops, embedded JS blocks.
- **Signature Help** — Function parameter hints for Perchance built‑ins and custom JS helpers.
- **Hover Info** — Show documentation for macros, variables, tables, and generator blocks.

---

## Navigation & Refactoring

- **Go to Definition** — Jump to table definitions, macro declarations, variable assignments, generator blocks.
- **Find All References** — Cross‑file reference tracking for tables, macros, and variables.
- **Rename Symbol** — Safe renaming for tables, macros, variables, and generators.
- **Document Symbols** — Outline view for tables, macros, generators, JS blocks.
- **Workspace Symbols** — Multi‑file search for named Perchance constructs.

---

## Diagnostics & Linting

- **Error Checking** — Undefined tables, missing macros, invalid weights, malformed blocks, unclosed brackets.
- **Warnings** — Deprecated syntax, unused variables, unreachable branches.
- **Code Actions** — Quick fixes for missing definitions, auto‑create table, auto‑generate macro stub.

---

## Formatting & Editing

- **Formatter** — Indentation, alignment of weights, consistent block structure, whitespace cleanup.
- **Organize Tables** — Sort entries, normalize weights, collapse duplicates.
- **Auto‑Insert** — Auto‑complete closing tags, braces, and generator blocks.

---

## Perchance‑Specific Tools

- **Generator Preview** — Run Perchance code and show generated text inside VSCode.
- **Seeded Output** — Deterministic generation with custom seeds.
- **Multi‑Run** — Generate N outputs for testing randomness.
- **Debug Mode** — Trace table calls, macro expansions, and weighted selection paths.
- **Table Visualization** — Graph view of table relationships and generator flow.

---

## Project‑Level Features

- **Workspace Indexing** — Scan all `.pjs` files for definitions, references, and metadata.
- **Dependency Graph** — Visual map of table → macro → generator dependencies.
- **Build System Integration** — Export compiled Perchance bundles, minify, validate.
- **Multi‑Root Workspace Support** — Handle Perchance projects spread across folders.

---

## Extension Settings & Options

- **Color Theme Overrides** — Custom scopes for tables, macros, variables, JS blocks.
- **Formatter Settings** — Indentation size, weight alignment, block spacing.
- **Lint Rules** — Enable/disable warnings, strict mode, unused symbol detection.
- **Preview Settings** — Seed, number of runs, debug tracing, output formatting.
- **Snippets Toggle** — Enable/disable snippet packs.
- **Language Server Options** — Performance tuning, caching, indexing behavior.

---

## Advanced / Optional Features

- **Embedded JS Support** — Syntax highlighting, completion, linting inside JS blocks.
- **Embedded HTML Support** — Highlighting and completion for HTML inside Perchance templates.
- **Unit Testing** — Write tests for generators and tables.
- **Export Tools** — Export to JSON, bundle, or external runtime formats.
- **AI‑Assisted Generator Design** — Suggest tables, macros, or expansions based on context.
