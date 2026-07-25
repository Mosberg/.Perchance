#!/usr/bin/env python3
import html
import json
import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

APP_TITLE = "Perchance Web Scraper"
DEFAULT_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

FAVICON_DATA_URI = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
    "%3Crect width='64' height='64' rx='14' fill='%231a1a1a'/%3E"
    "%3Cpath d='M20 16h15c8 0 13 4 13 11 0 5-2 8-7 10 6 2 9 6 9 12 0 9-7 15-18 15H20V16zm10 8v10h5c4 0 6-2 6-5s-2-5-6-5h-5zm0 18v12h7c4 0 7-2 7-6s-3-6-8-6h-6z' fill='white'/%3E"
    "%3C/svg%3E"
)

WRAPPER_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <meta name="color-scheme" content="dark light">
  <link rel="icon" href="{favicon}">
  <style>
    :root {{
      color-scheme: dark light;
      --bg: #111827;
      --fg: #f9fafb;
      --panel: rgba(17, 24, 39, 0.82);
      --muted: #9ca3af;
      --accent: #22c55e;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; margin: 0; }}
    body {{
      display: grid;
      place-items: center;
      background:
        radial-gradient(circle at top, rgba(34, 197, 94, 0.16), transparent 40%),
        linear-gradient(180deg, #0b1020 0%, #111827 100%);
      color: var(--fg);
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .shell {{
      width: min(92vw, 980px);
      min-height: min(84vh, 820px);
      display: grid;
      grid-template-rows: auto 1fr;
      background: var(--panel);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 20px;
      overflow: hidden;
      backdrop-filter: blur(16px);
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
    }}
    .header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 16px 20px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .title {{ font-size: 1rem; font-weight: 700; letter-spacing: 0.02em; }}
    .status {{ font-size: 0.875rem; color: var(--muted); }}
    iframe {{ width: 100%; height: 100%; border: 0; background: white; }}
    .loader {{
      position: fixed;
      inset: 0;
      display: grid;
      place-items: center;
      background: rgba(11, 16, 32, 0.72);
      transition: opacity 180ms ease;
      z-index: 10;
    }}
    .loader[data-hidden="true"] {{ opacity: 0; pointer-events: none; }}
    .loader__card {{ text-align: center; padding: 24px 28px; }}
    .spinner {{
      width: 44px;
      height: 44px;
      margin: 0 auto 12px;
      border-radius: 999px;
      border: 3px solid rgba(255, 255, 255, 0.18);
      border-top-color: var(--accent);
      animation: spin 0.85s linear infinite;
    }}
    .loader__title {{ font-weight: 700; margin-bottom: 6px; }}
    .loader__text {{ color: var(--muted); font-size: 0.9375rem; }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  </style>
</head>
<body>
  <div class="loader" id="loader" aria-live="polite">
    <div class="loader__card">
      <div class="spinner" aria-hidden="true"></div>
      <div class="loader__title">Loading Perchance export</div>
      <div class="loader__text">Bootstrapping the saved wrapper and embedded source.</div>
    </div>
  </div>

  <div class="shell">
    <header class="header">
      <div class="title">{title}</div>
      <div class="status">Saved from {source_url}</div>
    </header>
    <iframe src="{escaped_url}" title="{title}" loading="eager"></iframe>
  </div>

  <script>
    const loader = document.getElementById("loader");
    window.addEventListener("load", () => loader.setAttribute("data-hidden", "true"), { once: true });
    setTimeout(() => loader.setAttribute("data-hidden", "true"), 3000);
  </script>
</body>
</html>
"""


class PerchanceScraper:
    def __init__(self, timeout=DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def scrape_many(self, urls, output_dir, logger):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        summary = {"saved": 0, "failed": 0}

        for raw_url in urls:
            url = self.normalize_url(raw_url)
            if not url:
                logger(f"[skip] Invalid URL: {raw_url}")
                summary["failed"] += 1
                continue

            try:
                result = self.scrape_one(url, output_dir, logger)
                logger(f"[ok] Saved: {result['folder']}")
                summary["saved"] += 1
            except Exception as exc:
                logger(f"[error] {url} -> {exc}")
                summary["failed"] += 1

        logger(f"Done. Saved: {summary['saved']} | Failed: {summary['failed']}")
        return summary

    def scrape_one(self, url, output_dir, logger):
        logger(f"[fetch] {url}")
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        html_text = response.text

        title, slug = self.get_page_identity(url, html_text)
        folder = output_dir / slug
        folder.mkdir(parents=True, exist_ok=True)

        pjs_code = self.extract_model_script(html_text)
        if not pjs_code:
            raise ValueError('Could not find <script id="modelScript"> content')

        metadata = {
            "url": url,
            "title": title,
            "slug": slug,
            "fetched_from": response.url,
        }

        pjs_path = folder / "main.pjs"
        html_path = folder / "index.html"
        meta_path = folder / "metadata.json"

        pjs_path.write_text(pjs_code, encoding="utf-8")
        html_path.write_text(self.build_wrapper(title, url), encoding="utf-8")
        meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

        logger(f"[save] {pjs_path.name}, {html_path.name}, {meta_path.name}")
        return {
            "folder": str(folder),
            "pjs": str(pjs_path),
            "html": str(html_path),
            "meta": str(meta_path),
        }

    def extract_model_script(self, html_text):
        soup = BeautifulSoup(html_text, "html.parser")
        node = soup.find("script", id="modelScript")

        if node and node.string is not None:
            return node.string.strip() + "\n"

        if node:
            return node.get_text("", strip=False).strip() + "\n"

        match = re.search(
            r'<script[^>]*id=["\\\']modelScript["\\\'][^>]*>(.*?)</script>',
            html_text,
            re.IGNORECASE | re.DOTALL,
        )
        if match:
            return html.unescape(match.group(1)).strip() + "\n"

        return None

    def get_page_identity(self, url, html_text):
        parsed = urlparse(url)
        raw_slug = parsed.path.strip("/") or parsed.netloc.split(".")[0] or "perchance-item"
        raw_slug = raw_slug.split("/")[0]
        slug = self.slugify(raw_slug)

        soup = BeautifulSoup(html_text, "html.parser")
        title_node = soup.find("title")
        title = title_node.get_text(" ", strip=True) if title_node else slug.replace("-", " ").title()
        return title, slug

    def build_wrapper(self, title, source_url):
        return WRAPPER_TEMPLATE.format(
            title=html.escape(title),
            source_url=html.escape(source_url),
            escaped_url=html.escape(source_url, quote=True),
            favicon=FAVICON_DATA_URI,
        )

    @staticmethod
    def normalize_url(raw):
        if not raw:
            return None

        candidate = raw.strip()
        if not candidate:
            return None

        if not re.match(r"^https?://", candidate, re.IGNORECASE):
            candidate = "https://" + candidate.lstrip("/")

        parsed = urlparse(candidate)
        if not parsed.netloc:
            return None

        return candidate

    @staticmethod
    def slugify(value):
        value = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
        value = re.sub(r"-+", "-", value).strip("-._")
        return value or "perchance-item"


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=16)
        self.master = master
        self.scraper = PerchanceScraper()
        self.log_queue = queue.Queue()
        self.output_dir = tk.StringVar(value=str(Path.cwd() / "perchance_exports"))
        self._build_ui()
        self._poll_logs()

    def _build_ui(self):
        self.master.title(APP_TITLE)
        self.master.geometry("980x760")
        self.master.minsize(880, 660)

        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)

        ttk.Label(
            header,
            text="Perchance Generator / Plugin Web Scraper",
            font=("Segoe UI", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            header,
            text="Paste one Perchance URL per line. The scraper saves main.pjs, index.html, and metadata.json for each entry.",
            wraplength=900,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        input_frame = ttk.LabelFrame(self, text="URLs", padding=12)
        input_frame.grid(row=1, column=0, sticky="nsew")
        input_frame.columnconfigure(0, weight=1)
        input_frame.rowconfigure(0, weight=1)

        self.url_text = tk.Text(input_frame, height=12, wrap="word", undo=True)
        self.url_text.grid(row=0, column=0, sticky="nsew")

        output_frame = ttk.LabelFrame(self, text="Output", padding=12)
        output_frame.grid(row=2, column=0, sticky="ew", pady=12)
        output_frame.columnconfigure(1, weight=1)

        ttk.Label(output_frame, text="Folder").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(output_frame, textvariable=self.output_dir).grid(row=0, column=1, sticky="ew")
        ttk.Button(output_frame, text="Browse...", command=self.choose_output_dir).grid(row=0, column=2, padx=(8, 0))

        actions = ttk.Frame(output_frame)
        actions.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        actions.columnconfigure(4, weight=1)

        self.scrape_button = ttk.Button(actions, text="Scrape URLs", command=self.start_scrape)
        self.scrape_button.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Load Example URLs", command=self.load_examples).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text="Clear URLs", command=self.clear_urls).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(actions, text="Open Output Folder", command=self.open_output_folder).grid(row=0, column=3)

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(actions, textvariable=self.status_var).grid(row=0, column=5, sticky="e")

        log_frame = ttk.LabelFrame(self, text="Log", padding=12)
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=18,
            wrap="word",
            state="disabled",
            background="#111827",
            foreground="#f9fafb",
            insertbackground="#f9fafb",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def choose_output_dir(self):
        path = filedialog.askdirectory(initialdir=self.output_dir.get() or str(Path.cwd()))
        if path:
            self.output_dir.set(path)

    def load_examples(self):
        examples = "\n".join([
            "https://perchance.org/ai-character-chat",
            "https://perchance.org/text-adventure-generator",
            "https://perchance.org/importable-instance-plugin",
        ])
        self.url_text.delete("1.0", tk.END)
        self.url_text.insert("1.0", examples)

    def clear_urls(self):
        self.url_text.delete("1.0", tk.END)

    def open_output_folder(self):
        path = Path(self.output_dir.get()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        try:
            import os
            os.startfile(path)
        except Exception:
            messagebox.showinfo("Output Folder", f"Saved output directory:\n{path}")

    def start_scrape(self):
        urls = [line.strip() for line in self.url_text.get("1.0", tk.END).splitlines() if line.strip()]
        if not urls:
            messagebox.showwarning(APP_TITLE, "Paste at least one URL.")
            return

        out_dir = self.output_dir.get().strip()
        if not out_dir:
            messagebox.showwarning(APP_TITLE, "Choose an output folder.")
            return

        self.scrape_button.configure(state="disabled")
        self.status_var.set("Scraping...")
        self._log(f"Starting scrape for {len(urls)} URL(s)...")

        thread = threading.Thread(target=self._run_scrape, args=(urls, out_dir), daemon=True)
        thread.start()

    def _run_scrape(self, urls, out_dir):
        try:
            summary = self.scraper.scrape_many(urls, out_dir, self._queue_log)
            self.log_queue.put(("done", summary))
        except Exception as exc:
            self.log_queue.put(("fatal", str(exc)))

    def _queue_log(self, message):
        self.log_queue.put(("log", message))

    def _poll_logs(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "done":
                    self.status_var.set(f"Complete: {payload['saved']} saved, {payload['failed']} failed")
                    self.scrape_button.configure(state="normal")
                    messagebox.showinfo(APP_TITLE, f"Finished. Saved: {payload['saved']} | Failed: {payload['failed']}")
                elif kind == "fatal":
                    self.status_var.set("Failed")
                    self.scrape_button.configure(state="normal")
                    self._log(f"[fatal] {payload}")
                    messagebox.showerror(APP_TITLE, payload)
        except queue.Empty:
            pass

        self.after(120, self._poll_logs)

    def _log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")


def main():
    root = tk.Tk()
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()