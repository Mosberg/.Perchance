"""
Perchance Web-Scraper (Tkinter GUI)
====================================

Paste any number of perchance.org generator/plugin URLs, choose an output
folder, and this tool will download each generator's raw `.perchance` source
and save it as two files:

    <output_folder>/<generator_name>/<generator_name>.pjs   -> the Perchance lists (main.pjs)
    <output_folder>/<generator_name>/<generator_name>.html -> the Perchance HTML (index.html) with a favicon + a tiny loader wrapper

How it works
------------
The public perchance.org API endpoint

    https://perchance.org/api/getGeneratorsAndDependencies?generatorNames=name1,name2,...

returns JSON like:

    {"success": true,
     "generators": {
        "minimal": {"name":"minimal", "imports":["common-noun"],
                    "code":"// ...", "lastEditTime": ...},
        ...
     }}

The `code` field is exactly the contents of a generator's `main.pjs`
(the hierarchical list source). The API does NOT expose the HTML body, so for
the `.html` file we additionally fetch the generator's live page and extract
the `<script id="preloaded-generator-data">` tag, which holds URL-encoded JSON
containing `modelText` (== code) and `outputTemplate` (== the index.html body).
`outputTemplate` is the real Perchance HTML, so we wrap it with a favicon +
a minimal harness that mirrors how perchance serves `index.html`.

Run:
    python3 src/perchance_scraper.py

Requires only the Python standard library (tkinter, urllib, json, re, os,
threading, html.parser). No pip install needed.
"""

import os
import re
import json
import threading
import urllib.request
import urllib.parse
import html
from html.parser import HTMLParser
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext

# --------------------------------------------------------------------------- #
# Networking helpers
# --------------------------------------------------------------------------- #

USER_AGENT = (
    "Mozilla/5.0 (compatible; PerchanceWebScraper/1.0; " "+https://perchance.org/)"
)
TIMEOUT = 30  # seconds per request


def _fetch(url):
    """GET a URL and return its bytes. Raises urllib.error.URLError on failure."""
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _fetch_text(url):
    return _fetch(url).decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# URL parsing
# --------------------------------------------------------------------------- #

# Accept formats like:
#   https://perchance.org/my-cool-generator
#   https://perchance.org/my-cool-generator#edit
#   perchance.org/my-cool-generator
#   my-cool-generator            (bare name)
# Generators/plugins are lowercase letters, digits and hyphens.
_NAME_RE = re.compile(r"[a-z0-9-]+")


def parse_urls(raw_text):
    """Return an ordered list of unique generator/plugin names from a blob."""
    names = []
    seen = set()
    for line in raw_text.replace(",", "\n").splitlines():
        line = line.strip()
        if not line:
            continue
        # strip scheme
        if "://" in line:
            line = line.split("://", 1)[1]
        # drop fragment
        line = line.split("#", 1)[0]
        # drop leading perchance.org/ if present
        if line.startswith("perchance.org/"):
            line = line[len("perchance.org/") :]
        # drop query
        line = line.split("?", 1)[0]
        # drop trailing slashes
        line = line.strip("/").strip()
        m = _NAME_RE.fullmatch(line)
        if not m:
            continue
        name = m.group(0)
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


# --------------------------------------------------------------------------- #
# Perchance data extraction
# --------------------------------------------------------------------------- #


class _PreloadedDataParser(HTMLParser):
    """Tiny parser to pull the text of <script id="preloaded-generator-data">."""

    def __init__(self):
        super().__init__()
        self.capturing = False
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            for k, v in attrs:
                if k == "id" and v == "preloaded-generator-data":
                    self.capturing = True
                    break

    def handle_endtag(self, tag):
        if tag == "script":
            self.capturing = False

    def handle_data(self, data):
        if self.capturing:
            self.buffer.append(data)

    def get_text(self):
        return "".join(self.buffer)


def extract_preloaded_data(page_html):
    """Given a perchance.org generator page's HTML, return the decoded JSON
    object from <script id="preloaded-generator-data"> (or None if absent)."""
    parser = _PreloadedDataParser()
    try:
        parser.feed(page_html)
    except Exception:
        pass
    raw = parser.get_text().strip()
    if not raw:
        return None
    try:
        return json.loads(urllib.parse.unquote(raw))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# The actual scraping of one generator
# --------------------------------------------------------------------------- #

# Inline SVG favicon (purple "P"-ish mark) as a data URL. Used in the generated
# HTML wrapper so each file is self-contained with no external asset dependency.
FAVICON_DATA_URL = "data:image/svg+xml," + urllib.parse.quote(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="12" fill="#5b21b6"/>'
    '<text x="32" y="44" font-size="40" text-anchor="middle" '
    'fill="#fff" font-family="Arial,sans-serif" font-weight="bold">P</text>'
    "</svg>"
)


def _safe_name(name):
    """Sanitize a generator/plugin name into a filesystem-safe folder/file name."""
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", name).strip("._")
    return cleaned or "generator"


def fetch_generator(name, log):
    """Fetch one generator's data. Returns a dict with keys:
       name, code (pjs source), html (outputTemplate or empty), imports.
    Raises on hard failure."""
    # First the API for the code (main.pjs).
    api_url = (
        "https://perchance.org/api/getGeneratorsAndDependencies"
        "?generatorNames=" + urllib.parse.quote(name)
    )
    log(f"[{name}] fetching API…")
    api_bytes = _fetch(api_url)
    api = json.loads(api_bytes.decode("utf-8", errors="replace"))
    if not api.get("success") or name not in api.get("generators", {}):
        raise RuntimeError(f"generator '{name}' not found via API")
    gdata = api["generators"][name]
    code = gdata.get("code", "")
    imports = gdata.get("imports", [])

    # Then the live page for the HTML body (outputTemplate).
    page_url = "https://perchance.org/" + urllib.parse.quote(name)
    html_body = ""
    try:
        log(f"[{name}] fetching HTML page…")
        page = _fetch_text(page_url)
        pre = extract_preloaded_data(page)
        if pre:
            if not code:
                code = pre.get("modelText", "") or code
            html_body = pre.get("outputTemplate", "") or ""
            # prefer the richer import list from preloaded data if present
            if not imports and pre.get("imports"):
                imports = pre["imports"]
            log(f"[{name}] HTML extracted ({len(html_body)} chars)")
        else:
            log(f"[{name}] WARNING: #preloaded-generator-data not found on page")
    except Exception as e:
        log(f"[{name}] WARNING: could not fetch HTML page: {e}")

    return {"name": name, "code": code, "html": html_body, "imports": imports}


def build_wrapper_html(name, output_template):
    """Wrap the Perchance outputTemplate (the real index.html body) in a
    minimal standalone HTML document with a favicon. Mirrors how perchance
    serves index.html: the body is the generator's HTML content."""
    body = (
        output_template
        if output_template
        else (
            "<!-- No outputTemplate was available for this generator. -->\n"
            "<h1>" + html.escape(name) + "</h1>\n<p>(HTML body could not be "
            "retrieved.)</p>\n"
        )
    )
    title = html.escape(name) + " \u2014 Perchance"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, '
        'initial-scale=1">\n'
        '  <link rel="icon" href="' + FAVICON_DATA_URL + '">\n'
        "  <title>" + title + "</title>\n"
        "  <style>\n"
        "    html { color-scheme: light dark; }\n"
        "    body { margin: 0; text-align: center; font-family: sans-serif; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n" + body + "\n</body>\n</html>\n"
    )


# --------------------------------------------------------------------------- #
# Output writing
# --------------------------------------------------------------------------- #


def save_generator(out_root, info, log):
    """Write <out_root>/<name>/<name>.pjs and .html. Returns (pjs_path, html_path)."""
    folder = os.path.join(out_root, _safe_name(info["name"]))
    os.makedirs(folder, exist_ok=True)

    base = _safe_name(info["name"])
    pjs_path = os.path.join(folder, base + ".pjs")
    html_path = os.path.join(folder, base + ".html")

    with open(pjs_path, "w", encoding="utf-8") as f:
        f.write(
            info["code"]
            if info["code"]
            else "// (no modelText/code returned for '%s')\n" % info["name"]
        )
    log(f"[{info['name']}] wrote {pjs_path} ({len(info['code'])} chars)")

    wrapper = build_wrapper_html(info["name"], info["html"])
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(wrapper)
    log(f"[{info['name']}] wrote {html_path} ({len(wrapper)} chars)")

    return pjs_path, html_path


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #


class ScraperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Perchance Web-Scraper")
        self.geometry("780x620")
        self.minsize(620, 480)
        self.configure(padx=14, pady=14)

        self.output_dir = tk.StringVar()
        self.url_text = tk.StringVar()
        self.running = False

        self._build_ui()

    def _build_ui(self):
        pad = {"pady": (0, 8)}

        # --- URLs input ---
        ttk.Label(
            self,
            text="Perchance generator / plugin URLs "
            "(one per line, or comma-separated):",
        ).pack(anchor="w", **pad)

        self.urls_box = scrolledtext.ScrolledText(
            self, height=9, wrap="word", font=("TkFixedFont", 10)
        )
        self.urls_box.pack(fill="both", expand=True, **pad)
        self.urls_box.insert(
            "1.0",
            "https://perchance.org/minimal\n" "https://perchance.org/ai-text-plugin\n",
        )

        # --- Output folder ---
        row = ttk.Frame(self)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="Output folder:").pack(side="left")
        self.dir_entry = ttk.Entry(row, textvariable=self.output_dir)
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=(6, 6))
        self.browse_btn = ttk.Button(row, text="Browse…", command=self._choose_dir)
        self.browse_btn.pack(side="left")

        # default output dir to cwd/perchance_scraped
        self.output_dir.set(os.path.join(os.getcwd(), "perchance_scraped"))

        # --- Controls ---
        ctl = ttk.Frame(self)
        ctl.pack(fill="x", **pad)
        self.scrape_btn = ttk.Button(
            ctl, text="\u25b6  Scrape", command=self._start_scrape
        )
        self.scrape_btn.pack(side="left")
        self.clear_btn = ttk.Button(ctl, text="Clear log", command=self._clear_log)
        self.clear_btn.pack(side="left", padx=(8, 0))
        self.progress = ttk.Progressbar(ctl, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(12, 0))

        # --- Log console ---
        ttk.Label(self, text="Log:").pack(anchor="w", **pad)
        self.log_box = scrolledtext.ScrolledText(
            self, height=10, wrap="word", state="disabled", font=("TkFixedFont", 9)
        )
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_config("error", foreground="#c62828")
        self.log_box.tag_config("ok", foreground="#2e7d32")

    # ---- helpers ----
    def _choose_dir(self):
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self.output_dir.set(d)

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
        self.scrape_btn.configure(state="disabled" if running else "normal")

    # ---- main action ----
    def _start_scrape(self):
        if self.running:
            return
        raw = self.urls_box.get("1.0", "end")
        names = parse_urls(raw)
        out_dir = self.output_dir.get().strip()
        if not names:
            self._log("No valid URLs found in the input box.", "error")
            return
        if not out_dir:
            self._log("Please choose an output folder.", "error")
            return

        self._set_running(True)
        self.progress["value"] = 0
        self.progress["maximum"] = len(names)
        self._log("Starting scrape of %d generator(s) -> %s" % (len(names), out_dir))
        t = threading.Thread(
            target=self._scrape_worker, args=(names, out_dir), daemon=True
        )
        t.start()

    def _scrape_worker(self, names, out_dir):
        ok = 0
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            self.after(0, self._log, "Cannot create output folder: %s" % e, "error")
            self.after(0, self._set_running, False)
            return

        for i, name in enumerate(names):
            try:
                info = fetch_generator(name, lambda m: self.after(0, self._log, m))
                self.after(
                    0,
                    save_generator,
                    out_dir,
                    info,
                    lambda m: self.after(0, self._log, m),
                )
                self.after(0, self._log, "\u2713 Done: %s" % name, "ok")
                ok += 1
            except Exception as e:
                self.after(0, self._log, "\u2717 Failed: %s -> %s" % (name, e), "error")
            finally:
                self.after(0, self._bump_progress, i + 1)

        self.after(0, self._log, "Finished. %d/%d succeeded." % (ok, len(names)), "ok")
        self.after(0, self._set_running, False)

    def _bump_progress(self, value):
        self.progress["value"] = value


def main():
    app = ScraperApp()
    app.mainloop()


if __name__ == "__main__":
    main()
