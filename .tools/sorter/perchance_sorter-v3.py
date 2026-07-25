"""
Perchance Folder Sorter (Tkinter GUI)
======================================

Scans the four category folders (generators/, plugins/, custom/, styles/) in
your .Perchance repo, detects items that are in the wrong folder, shows a
preview table with suggested moves, and lets you confirm/skip each one before
executing.

Detection rules (checked in priority order)
-------------------------------------------
1. Random IDs — 8-10 char alphanumeric names stay in their current folder
   (ambiguous: could be user's own unnamed generators or scraped ones).
2. plugins/  — name ends with "-plugin" OR is in the official perchance.org
   plugin list (78 known plugins).
3. styles/   — name contains "styles", "style-pack", or matches style patterns.
4. custom/   — personal generators: contains "moss"/"mosberg", matches personal
   project patterns (ai-calculator, t2i-, perchance-, nsfw, *-kit, etc.).
5. generators/ — everything else (default).

The GUI shows all suggested moves in a table with checkboxes. Uncheck any
you disagree with, then click "Move checked" to execute. A log console shows
progress and results.

Run:
    python3 src/perchance_sorter.py
"""

import os
import re
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext


# --------------------------------------------------------------------------- #
# Known plugins (from perchance.org/plugins)
# --------------------------------------------------------------------------- #

KNOWN_PLUGINS = {
    "a-an-plugin", "ai-text-plugin", "background-audio-plugin",
    "background-image-plugin", "be-plugin", "bug-report-plugin",
    "comments-plugin", "conjugate-plugin", "consumable-leaf-list-plugin",
    "consumable-list-loop-plugin", "copy-text-plugin",
    "create-instance-plugin", "create-instances-plugin", "date-plugin",
    "dice-plugin", "docs-plugin", "download-button-plugin",
    "dynamic-import-plugin", "exclude-items-plugin", "favicon-plugin",
    "filter-list-plugin", "fixed-until-reload-plugin", "flat-avatar-plugin",
    "font-plugin", "fullscreen-button-plugin", "generator-stats-plugin",
    "google-sheets-plugin", "goto-plugin", "image-layer-combiner-plugin",
    "image-plugin", "join-lists-plugin", "kv-plugin", "layout-maker-plugin",
    "literal-plugin", "lockable-list-plugin", "locker-plugin",
    "make-table-plugin", "markdown-plugin", "markov-chain-plugin",
    "navbar-plugin", "nested-plugin", "number-set-plugin",
    "numerals-to-ordinal-words-plugin", "numerals-to-ordinals-plugin",
    "numerals-to-words-plugin", "pattern-maker-plugin", "plural-plugin",
    "press-enter-plugin", "pride-plugin", "print-button-plugin",
    "random-decimal-plugin", "random-image-plugin", "random-integer-plugin",
    "random-select-plugin", "remember-plugin", "roll-table-plugin",
    "roman-numerals-plugin", "rpg-icon-plugin", "secret-plugin",
    "seeder-plugin", "select-all-leaves-plugin", "select-leaf-plugin",
    "select-leaves-plugin", "select-range-plugin", "select-until-plugin",
    "sum-odds-plugin", "super-fetch-plugin", "tabs-plugin",
    "tap-anywhere-plugin", "tap-plugin", "text-to-image-plugin",
    "text-to-speech-plugin", "title-case-plugin", "tldraw-plugin",
    "tooltip-plugin", "tornado-plugin", "typewriter-plugin",
    "upload-plugin", "url-params-plugin", "wheel-plugin",
}

CATEGORIES = ("generators", "plugins", "custom", "styles")

# Patterns that indicate a personal/custom generator.
# These are the user's own creations (not scraped from others).
_CUSTOM_PATTERNS = [
    # personal identifiers
    re.compile(r"moss", re.I),
    re.compile(r"mosberg", re.I),
    re.compile(r"^my[-]", re.I),
    re.compile(r"durhuuz", re.I),
    re.compile(r"skagen", re.I),
    re.compile(r"^dansk", re.I),
    re.compile(r"^danke", re.I),
    re.compile(r"erotisk", re.I),
    re.compile(r"^spiludbydere", re.I),
    re.compile(r"^mors-dag", re.I),
    re.compile(r"^tahh", re.I),
    re.compile(r"^mos[-]", re.I),
    re.compile(r"^msg-chat", re.I),
    re.compile(r"^normal-tekst", re.I),
    # personal AI projects
    re.compile(r"^ai-calculator", re.I),
    re.compile(r"^ai-messenger", re.I),
    re.compile(r"^ai-character-chat(?!-moss)", re.I),
    re.compile(r"^ai-character-nsfw", re.I),
    re.compile(r"^ai-character-generator-nsfw", re.I),
    re.compile(r"^ai-character-generator-mosberg", re.I),
    re.compile(r"^ai-character-generator-moss", re.I),
    re.compile(r"^ai-code-generator", re.I),
    re.compile(r"^ai-text-rewriter", re.I),
    re.compile(r"^ai-text-to-nsfw", re.I),
    re.compile(r"^ai-text-to-image-generator-moss", re.I),
    re.compile(r"^ai-text-converter", re.I),
    re.compile(r"^ai-fuck-chat", re.I),
    re.compile(r"^ai-companions", re.I),
    re.compile(r"^ai-lustlife", re.I),
    re.compile(r"^ai-hentai", re.I),
    re.compile(r"^ai-nsfw", re.I),
    re.compile(r"^ai-pokemon-generator-moss", re.I),
    re.compile(r"^ai-image-to-prompt", re.I),
    re.compile(r"^ai-image-describer", re.I),
    re.compile(r"^ai-image-generator-pro", re.I),
    re.compile(r"^ai-text2image", re.I),
    re.compile(r"^ai-text-to-image-studio", re.I),
    re.compile(r"^ai-winrar", re.I),
    re.compile(r"^ai-browser", re.I),
    re.compile(r"^ai-notepad", re.I),
    re.compile(r"^ai-calendar", re.I),
    re.compile(r"^ai-adventure-writer", re.I),
    re.compile(r"^ai-anime-character", re.I),
    re.compile(r"^ai-json", re.I),
    re.compile(r"^ai-lpc", re.I),
    re.compile(r"^ai-minecraft", re.I),
    re.compile(r"^ai-text---image-studio", re.I),
    # NSFW / adult content
    re.compile(r"nsfw", re.I),
    re.compile(r"^adult", re.I),
    re.compile(r"^porno", re.I),
    re.compile(r"^hentai", re.I),
    re.compile(r"^sissygasm", re.I),
    re.compile(r"^unrestricted-nsfw", re.I),
    re.compile(r"^persona-studio-adult", re.I),
    re.compile(r"^dnd-5e-ultimate-sheet-nsfw", re.I),
    re.compile(r"^the-ai-hentai", re.I),
    re.compile(r"^advanced-text-to-porno", re.I),
    re.compile(r"^random-character-fuck", re.I),
    re.compile(r"^random-character-chat", re.I),
    re.compile(r"^custom-ai-character", re.I),
    # personal frameworks / tools
    re.compile(r"^t2i[-]", re.I),
    re.compile(r"^t2t[-]", re.I),
    re.compile(r"^text2image[-]", re.I),
    re.compile(r"^perchance[-]", re.I),
    re.compile(r"^json[xz]?", re.I),
    re.compile(r"^listsx", re.I),
    re.compile(r"^listx[-]", re.I),
    re.compile(r"^select-listx", re.I),
    re.compile(r"[-]kit$", re.I),
    re.compile(r"^custom-t2i", re.I),
    re.compile(r"^gw-framework", re.I),
    re.compile(r"^ultimate[-]", re.I),
    re.compile(r"^the-ai-generator", re.I),
    re.compile(r"^the-ai-hub", re.I),
    re.compile(r"^the-list-plugin", re.I),
    re.compile(r"^the-perchance-editor", re.I),
    re.compile(r"^creation-kit", re.I),
    re.compile(r"^plugin-architect", re.I),
    re.compile(r"^vs-code-extension", re.I),
    re.compile(r"^mysql-perchance", re.I),
    # personal game projects
    re.compile(r"^pokemon-yellow", re.I),
    re.compile(r"^pokemon-forge", re.I),
    re.compile(r"^pokeemerald", re.I),
    re.compile(r"^minecraft[-]", re.I),
    re.compile(r"^fabric[-]", re.I),
    re.compile(r"^luau[-]", re.I),
    re.compile(r"^lu-ai", re.I),
    re.compile(r"^ltx[-]", re.I),
    re.compile(r"^ant[-]", re.I),
    re.compile(r"^antss", re.I),
    re.compile(r"^ant-colony", re.I),
    re.compile(r"^m-o-m", re.I),
    re.compile(r"^grindr", re.I),
    re.compile(r"^neon[-]", re.I),
    re.compile(r"^quantum-dash", re.I),
    re.compile(r"^pro-slush", re.I),
    re.compile(r"^grand-woods", re.I),
    re.compile(r"^rarity-and-relics", re.I),
    re.compile(r"^waterfall-climber", re.I),
    re.compile(r"^tree-hustler", re.I),
    re.compile(r"^photon-harvest", re.I),
    re.compile(r"^monster-quest", re.I),
    re.compile(r"^space-rock", re.I),
    re.compile(r"^bunnytrials", re.I),
    re.compile(r"^neural-slots", re.I),
    re.compile(r"^neon-slots", re.I),
    re.compile(r"^solitare", re.I),
    re.compile(r"^r-bunnytrials", re.I),
    re.compile(r"^spore-cell", re.I),
    re.compile(r"^my-awakening", re.I),
    re.compile(r"^old-school-runescape", re.I),
    re.compile(r"^osrs", re.I),
    re.compile(r"^runescape", re.I),
    re.compile(r"^grind", re.I),
    re.compile(r"^beyond-the-bobber", re.I),
    # personal character/metadata tools
    re.compile(r"^character-carousel", re.I),
    re.compile(r"^character-forging", re.I),
    re.compile(r"^character-metadata", re.I),
    re.compile(r"^character-output", re.I),
    re.compile(r"^character-prompt", re.I),
    re.compile(r"^character-universe", re.I),
    re.compile(r"^character-visual", re.I),
    re.compile(r"^character-working", re.I),
    re.compile(r"^enhanced-working-character", re.I),
    re.compile(r"^simple-working-character", re.I),
    re.compile(r"^ultra-detailed-character", re.I),
    re.compile(r"^generate-character", re.I),
    re.compile(r"^advanced-character", re.I),
    re.compile(r"^aetheria-character", re.I),
    re.compile(r"^fantasy-codex", re.I),
    re.compile(r"^mythos-mixer", re.I),
    re.compile(r"^alchemy-schema", re.I),
    # personal misc
    re.compile(r"^a-moaning-world", re.I),
    re.compile(r"^acg-modes", re.I),
    re.compile(r"^add-poke", re.I),
    re.compile(r"^advanced-ai-image-generator", re.I),
    re.compile(r"^advertisement-ad-agency", re.I),
    re.compile(r"^apple-airtag", re.I),
    re.compile(r"^fresh-windows-install", re.I),
    re.compile(r"^gds0", re.I),
    re.compile(r"^gds1", re.I),
    re.compile(r"^generate-25-character", re.I),
    re.compile(r"^generator-gen", re.I),
    re.compile(r"^load-from-github", re.I),
    re.compile(r"^next-gen-minecraft", re.I),
    re.compile(r"^perchancejsonc", re.I),
    re.compile(r"^reddit-ai-character", re.I),
    re.compile(r"^scratchpad", re.I),
    re.compile(r"^transform-text", re.I),
    re.compile(r"^attpahig", re.I),
    re.compile(r"^m-o-m-s", re.I),
    re.compile(r"^000-00", re.I),
    re.compile(r"^3d-pkm", re.I),
    re.compile(r"^img-to-pixel-art", re.I),
    re.compile(r"^dynamic-software-dashboard", re.I),
    re.compile(r"^mos-ai-img", re.I),
    re.compile(r"^session-stats-plugin", re.I),
    re.compile(r"^year-range-and-creator-plugin", re.I),
    # other personal misc
    re.compile(r"^-------a", re.I),
    re.compile(r"^--perchance-gdscript-studio", re.I),
    re.compile(r"^00mtg", re.I),
    re.compile(r"^a-notebook-plugin", re.I),
    re.compile(r"^advanced-json-viewer", re.I),
    re.compile(r"^random-generators", re.I),
    re.compile(r"^universal-lpc-spritesheet", re.I),
    re.compile(r"^gkslyd", re.I),
    re.compile(r"^sad1356146", re.I),
]

# Patterns for style lists
_STYLE_PATTERNS = [
    re.compile(r"styles$", re.I),
    re.compile(r"style-pack", re.I),
    re.compile(r"^t2i-styles", re.I),
    re.compile(r"^t2t-styles", re.I),
    re.compile(r"text-to-image-styles", re.I),
    re.compile(r"text2image-style", re.I),
    re.compile(r"hentai-artist-styles", re.I),
    re.compile(r"art-styles", re.I),
]


def detect_category(name: str, current: str = "") -> str:
    """Detect which category folder a generator/plugin belongs in.

    If the name is a random perchance ID (8-10 char alphanumeric), it stays
    in its current folder — random IDs are ambiguous (could be the user's
    own unnamed generators or scraped generators from others).
    """
    # random perchance IDs: keep in current folder
    if re.match(r"^[a-z0-9]{8,10}$", name) and current:
        return current
    # plugins: highest priority
    if name in KNOWN_PLUGINS or name.endswith("-plugin"):
        return "plugins"
    # styles: check before custom so t2i-styles-mosberg-* go to styles
    for pat in _STYLE_PATTERNS:
        if pat.search(name):
            return "styles"
    # custom: personal generators
    for pat in _CUSTOM_PATTERNS:
        if pat.search(name):
            return "custom"
    # generators: default
    return "generators"


# --------------------------------------------------------------------------- #
# Scanner
# --------------------------------------------------------------------------- #

def scan_repo(repo_root: str):
    """Scan all four category folders. Returns list of dicts:
    [{name, current, suggested, path, files}, ...] for misplaced items."""
    misplaced = []
    for cat in CATEGORIES:
        cat_dir = os.path.join(repo_root, cat)
        if not os.path.isdir(cat_dir):
            continue
        for name in sorted(os.listdir(cat_dir)):
            item_dir = os.path.join(cat_dir, name)
            if not os.path.isdir(item_dir):
                continue
            suggested = detect_category(name, cat)
            if suggested != cat:
                files = sorted(os.listdir(item_dir))
                misplaced.append({
                    "name": name,
                    "current": cat,
                    "suggested": suggested,
                    "path": item_dir,
                    "files": files,
                })
    return misplaced


def move_item(item: dict, repo_root: str):
    """Move a generator folder from its current category to the suggested one."""
    dest_dir = os.path.join(repo_root, item["suggested"], item["name"])
    os.makedirs(os.path.dirname(dest_dir), exist_ok=True)
    if os.path.exists(dest_dir):
        # merge: copy files over, don't overwrite existing
        for f in item["files"]:
            src = os.path.join(item["path"], f)
            dst = os.path.join(dest_dir, f)
            if not os.path.exists(dst):
                shutil.move(src, dst)
        # remove source dir if empty
        try:
            os.rmdir(item["path"])
        except OSError:
            pass
    else:
        shutil.move(item["path"], dest_dir)


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #

class SorterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Perchance Folder Sorter")
        self.geometry("900x680")
        self.minsize(700, 520)
        self.configure(padx=14, pady=14)

        self.repo_dir = tk.StringVar()
        self.items = []          # all misplaced items
        self.check_vars = []     # BooleanVar per item
        self.running = False

        self._build_ui()

    def _build_ui(self):
        # --- Repo folder ---
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text="Repo folder:").pack(side="left")
        entry = ttk.Entry(row, textvariable=self.repo_dir)
        entry.pack(side="left", fill="x", expand=True, padx=(6, 6))
        ttk.Button(row, text="Browse\u2026", command=self._choose_dir).pack(side="left")

        # --- Scan + move buttons ---
        ctl = ttk.Frame(self)
        ctl.pack(fill="x", pady=(0, 8))
        self.scan_btn = ttk.Button(ctl, text="\U0001f50d  Scan",
                                   command=self._start_scan)
        self.scan_btn.pack(side="left")
        self.move_btn = ttk.Button(ctl, text="\u25b6  Move checked",
                                   command=self._start_move, state="disabled")
        self.move_btn.pack(side="left", padx=(8, 0))
        self.checkall_btn = ttk.Button(ctl, text="Check all",
                                       command=self._check_all, state="disabled")
        self.checkall_btn.pack(side="left", padx=(8, 0))
        self.uncheckall_btn = ttk.Button(ctl, text="Uncheck all",
                                         command=self._uncheck_all, state="disabled")
        self.uncheckall_btn.pack(side="left", padx=(4, 0))
        self.clear_btn = ttk.Button(ctl, text="Clear log",
                                    command=self._clear_log)
        self.clear_btn.pack(side="right")
        self.progress = ttk.Progressbar(ctl, mode="determinate")
        self.progress.pack(side="right", fill="x", expand=True, padx=(12, 8))

        # --- Results table ---
        cols = ("check", "name", "current", "suggested", "files")
        self.tree = ttk.Treeview(self, columns=cols, show="headings",
                                 height=14)
        self.tree.heading("check", text="Move?")
        self.tree.heading("name", text="Generator name")
        self.tree.heading("current", text="Current folder")
        self.tree.heading("suggested", text="Suggested folder")
        self.tree.heading("files", text="Files")
        self.tree.column("check", width=50, anchor="center")
        self.tree.column("name", width=280)
        self.tree.column("current", width=110, anchor="center")
        self.tree.column("suggested", width=110, anchor="center")
        self.tree.column("files", width=200)
        self.tree.pack(fill="both", expand=True, pady=(0, 8))

        # tag colors for suggested folder
        self.tree.tag_configure("plugins", foreground="#1565c0")
        self.tree.tag_configure("styles", foreground="#6a1b9a")
        self.tree.tag_configure("custom", foreground="#e65100")
        self.tree.tag_configure("generators", foreground="#2e7d32")

        # click to toggle checkbox
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_click)

        # --- Log ---
        ttk.Label(self, text="Log:").pack(anchor="w", pady=(0, 4))
        self.log_box = scrolledtext.ScrolledText(self, height=8, wrap="word",
                                                 state="disabled",
                                                 font=("TkFixedFont", 9))
        self.log_box.pack(fill="both", expand=False)
        self.log_box.tag_config("error", foreground="#c62828")
        self.log_box.tag_config("ok", foreground="#2e7d32")
        self.log_box.tag_config("warn", foreground="#e65100")

    # ---- helpers ----
    def _choose_dir(self):
        d = filedialog.askdirectory(title="Choose .Perchance repo folder")
        if d:
            self.repo_dir.set(d)

    def _log(self, msg, tag=None):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n", tag if tag else ())
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self.update_idletasks()

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _set_running(self, running):
        self.running = running
        state = "disabled" if running else "normal"
        self.scan_btn.configure(state=state)
        self.move_btn.configure(state=state)
        self.checkall_btn.configure(state=state)
        self.uncheckall_btn.configure(state=state)

    # ---- scan ----
    def _start_scan(self):
        if self.running:
            return
        repo = self.repo_dir.get().strip()
        if not repo:
            self._log("Please choose the repo folder first.", "error")
            return
        if not os.path.isdir(repo):
            self._log("Folder does not exist: %s" % repo, "error")
            return

        self._set_running(True)
        self._log("Scanning %s \u2026" % repo)
        t = threading.Thread(target=self._scan_worker, args=(repo,),
                             daemon=True)
        t.start()

    def _scan_worker(self, repo):
        try:
            items = scan_repo(repo)
        except Exception as e:
            self.after(0, self._log, "Scan failed: %s" % e, "error")
            self.after(0, self._set_running, False)
            return

        self.after(0, self._populate_results, items)
        self.after(0, self._set_running, False)

    def _populate_results(self, items):
        # clear tree
        for child in self.tree.get_children():
            self.tree.delete(child)
        self.items = items
        self.check_vars = []

        if not items:
            self._log("\u2713 Everything is already in the correct folder!", "ok")
            self.move_btn.configure(state="disabled")
            self.checkall_btn.configure(state="disabled")
            self.uncheckall_btn.configure(state="disabled")
            return

        # summary
        summary = {}
        for it in items:
            key = "%s \u2192 %s" % (it["current"], it["suggested"])
            summary[key] = summary.get(key, 0) + 1
        for key, count in sorted(summary.items()):
            self._log("  %s: %d" % (key, count))
        self._log("Found %d misplaced item(s)." % len(items), "warn")

        for i, it in enumerate(items):
            var = tk.BooleanVar(value=True)
            self.check_vars.append(var)
            files_str = ", ".join(it["files"])
            iid = self.tree.insert("", "end", values=(
                "\u2611", it["name"], it["current"], it["suggested"],
                files_str
            ), tags=(it["suggested"],))
            # store iid on var for sync
            var._iid = iid

        self.move_btn.configure(state="normal")
        self.checkall_btn.configure(state="normal")
        self.uncheckall_btn.configure(state="normal")

    # ---- tree interaction ----
    def _on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != "#1":  # only toggle when clicking the "Move?" column
            # but also allow clicking anywhere on the row to toggle
            pass
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        # find the check var for this iid
        for var in self.check_vars:
            if getattr(var, "_iid", None) == iid:
                var.set(not var.get())
                self.tree.set(iid, "check", "\u2611" if var.get() else "\u2610")
                break

    def _check_all(self):
        for var in self.check_vars:
            var.set(True)
            if getattr(var, "_iid", None):
                self.tree.set(var._iid, "check", "\u2611")

    def _uncheck_all(self):
        for var in self.check_vars:
            var.set(False)
            if getattr(var, "_iid", None):
                self.tree.set(var._iid, "check", "\u2610")

    # ---- move ----
    def _start_move(self):
        if self.running:
            return
        checked = [it for it, var in zip(self.items, self.check_vars)
                   if var.get()]
        if not checked:
            self._log("Nothing checked to move.", "warn")
            return

        repo = self.repo_dir.get().strip()
        self._set_running(True)
        self.progress["value"] = 0
        self.progress["maximum"] = len(checked)
        self._log("Moving %d item(s)\u2026" % len(checked))
        t = threading.Thread(target=self._move_worker,
                             args=(checked, repo), daemon=True)
        t.start()

    def _move_worker(self, checked, repo):
        ok = 0
        for i, it in enumerate(checked):
            try:
                move_item(it, repo)
                self.after(0, self._log,
                           "\u2713 %s: %s \u2192 %s"
                           % (it["name"], it["current"], it["suggested"]),
                           "ok")
                ok += 1
            except Exception as e:
                self.after(0, self._log,
                           "\u2717 %s: %s" % (it["name"], e), "error")
            finally:
                self.after(0, self._bump_progress, i + 1)

        self.after(0, self._log,
                   "Done. %d/%d moved." % (ok, len(checked)), "ok")
        self.after(0, self._set_running, False)
        # re-scan after moving
        self.after(0, self._start_scan)

    def _bump_progress(self, value):
        self.progress["value"] = value


def main():
    app = SorterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
