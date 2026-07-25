// create-perchance-extension.js
// Generates a minimal VSCode extension scaffold for Perchance (.pjs)

const fs = require("fs");
const path = require("path");

function write(file, content) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content);
  console.log("✔ Created", file);
}

function main() {
  const root = "perchance-pjs-support";

  // --- package.json ---
  write(
    `${root}/package.json`,
    JSON.stringify(
      {
        name: "perchance-pjs-support",
        displayName: "Perchance (.pjs) Language Support",
        description: "Basic language support for Perchance generator files.",
        version: "0.0.1",
        publisher: "your-name",
        engines: { vscode: "^1.70.0" },
        categories: ["Programming Languages"],
        main: "./src/extension.js",
        activationEvents: ["onLanguage:perchance"],
        contributes: {
          languages: [
            {
              id: "perchance",
              aliases: ["Perchance", "perchance"],
              extensions: [".pjs", ".perchance"],
              configuration: "./language-configuration.json",
            },
          ],
          grammars: [
            {
              language: "perchance",
              scopeName: "source.perchance",
              path: "./syntaxes/perchance.tmLanguage.json",
            },
          ],
          snippets: [
            {
              language: "perchance",
              path: "./snippets/perchance.json",
            },
          ],
        },
      },
      null,
      2,
    ),
  );

  // --- language configuration ---
  write(
    `${root}/language-configuration.json`,
    JSON.stringify(
      {
        comments: { lineComment: "//" },
        brackets: [
          ["[", "]"],
          ["{", "}"],
        ],
        autoClosingPairs: [
          { open: "[", close: "]" },
          { open: "{", close: "}" },
        ],
        surroundingPairs: [
          { open: "[", close: "]" },
          { open: "{", close: "}" },
        ],
      },
      null,
      2,
    ),
  );

  // --- TextMate grammar ---
  write(
    `${root}/syntaxes/perchance.tmLanguage.json`,
    JSON.stringify(
      {
        scopeName: "source.perchance",
        patterns: [
          { include: "#comment" },
          { include: "#jsblock" },
          { include: "#alternation" },
        ],
        repository: {
          comment: {
            name: "comment.line.double-slash.perchance",
            match: "//.*$",
          },
          jsblock: {
            name: "meta.embedded.js.perchance",
            begin: "\\[",
            end: "\\]",
            patterns: [{ include: "source.js" }],
          },
          alternation: {
            name: "meta.alternation.perchance",
            begin: "\\{",
            end: "\\}",
            patterns: [{ match: "\\|" }],
          },
        },
      },
      null,
      2,
    ),
  );

  // --- extension.js ---
  write(
    `${root}/src/extension.js`,
    `const vscode = require("vscode");

function activate(context) {
  console.log("Perchance extension activated");

  const provider = {
    provideHover(document, position) {
      return new vscode.Hover("Perchance (.pjs) file");
    }
  };

  context.subscriptions.push(
    vscode.languages.registerHoverProvider("perchance", provider)
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
`,
  );

  // --- snippets ---
  write(
    `${root}/snippets/perchance.json`,
    JSON.stringify(
      {
        "Basic Table": {
          prefix: "table",
          body: ["${1:name}", "  ${2:item1}", "  ${3:item2}"],
          description: "Create a basic Perchance table",
        },
      },
      null,
      2,
    ),
  );

  // --- README ---
  write(
    `${root}/README.md`,
    `# Perchance (.pjs) Language Support

This is a minimal VSCode extension scaffold generated automatically.

Features:
- Syntax highlighting
- Basic hover provider
- Snippets
`,
  );

  // --- .vscodeignore ---
  write(
    `${root}/.vscodeignore`,
    `node_modules
.git
.vscode
`,
  );

  console.log("\n🎉 Perchance extension scaffold generated!");
}

main();
