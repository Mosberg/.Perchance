#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import html
import json
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup


APP_TITLE = "Perchance Web Scraper"
APP_SIZE = "1120x860"
DEFAULT_TIMEOUT = 30
REQUEST_DELAY = 0.15

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

FAVICON_DATA_URI = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
    "%3Crect width='64' height='64' rx='14' fill='%230f172a'/%3E"
    "%3Cpath d='M18 14h17c9 0 14 4 14 11 0 5-3 8-8 10 7 2 10 6 10 13 0 10-7 16-19 16H18V14zm11 8v10h6c4 0 7-2 7-5s-3-5-7-5h-6zm0 18v14h8c5 0 8-2 8-7 0-4-3-7-9-7h-7z' fill='white'/%3E"
    "%3C/svg%3E"
)

HTML_WRAPPER_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <meta name="color-scheme" content="dark light">
  <meta name="generator" content="Perchance Web Scraper">
  <link rel="icon" href="{favicon}">
  <style>
    :root {{
      color-scheme: dark light;
      --bg: #0f172a;
      --bg2: #111827;
      --panel: rgba(15, 23, 42, 0.84);
      --text: #f8fafc;
      --muted: #94a3b8;
      --accent: #22c55e;
      --border: rgba(255,255,255,0.09);
      --shadow: 0 24px 60px rgba(0,0,0,0.32);
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; margin: 0; }}
    body {{
      display: grid;
      place-items: center;
      min-height: 100%;
      background:
        radial-gradient(circle at top, rgba(34,197,94,0.14), transparent 34%),
        linear-gradient(180deg, var(--bg) 0%, var(--bg2) 100%);
      color: var(--text);
      font-family: Inter, "Segoe UI", system-ui, sans-serif;
    }}
    .app {{
      width: min(94vw, 1180px);
      min-height: min(88vh, 900px);
      display: grid;
      grid-template-rows: auto 1fr auto;
      border: 1px solid var(--border);
      border-radius: 18px;
      overflow: hidden;
      background: var(--panel);
      backdrop-filter: blur(16px);
      box-shadow: var(--shadow);
    }}
    .bar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 18px;
      border-bottom: 1px solid var(--border);
    }}
    .title {{
      font-weight: 700;
      font-size: 1rem;
      letter-spacing: 0.02em;
    }}
    .subtitle {{
      color: var(--muted);
      font-size: 0.875rem;
    }}
    .frame-wrap {{
      position: relative;
      min-height: 560px;
      background: #ffffff;
    }}
    iframe {{
      width: 100%;
      height: 100%;
      min-height: 560px;
      border: 0;
      display: block;
      background: white;
    }}
    .footer {{
      padding: 12px 18px;
      border-top: 1px solid var(--border);
      color: var(--muted);
      font-size: 0.875rem;
    }}
    .loader {{
      position: fixed;
      inset: 0;
      display: grid;
      place-items: center;
      background: rgba(2, 6, 23, 0.72);
      transition: opacity 180ms ease;
      z-index: 50;
    }}
    .loader[data-hidden="true"] {{
      opacity: 0;
      pointer-events: none;
    }}
    .loader__card {{
      width: min(90vw, 360px);
      text-align: center;
      padding: 24px;
      border-radius: 16px;
      background: rgba(15, 23, 42, 0.95);
      border: 1px solid var(--border);
      box-shadow: var(--shadow);
    }}
    .spinner {{
      width: 46px;
      height: 46px;
      margin: 0 auto 14px;
      border-radius: 999px;
      border: 3px solid rgba(255,255,255,0.14);
      border-top-color: var(--accent);
      animation: spin 0.9s linear infinite;
    }}
    .loader__title {{
      font-weight: 700;
      margin-bottom: 6px;
    }}
    .loader__text {{
      color: var(--muted);
      font-size: 0.94rem;
      line-height: 1.45;
    }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 0.875em;
    }}
    @keyframes spin {{
      to {{ transform: rotate(360deg); }}
    }}
  </style>
</head>
<body>
  <div class="loader" id="loader" aria-live="polite">
    <div class="loader__card">
      <div class="spinner" aria-hidden="true"></div>
      <div class="loader__title">Loading saved Perchance wrapper</div>
      <div class="loader__text">This exported wrapper points to the original Perchance page and keeps your extracted source beside it as <code>main.pjs</code>.</div>
    </div>
  </div>

  <main class="app">
    <header class="bar">
      <div>
        <div class="title">{title}</div>
        <div class="subtitle">{kind_label}</div>
      </div>
      <div class="subtitle">Source: {source_url}</div>
    </header>

    <section class="frame-wrap">
      <iframe
        src="{iframe_url}"
        title="{title}"
        loading="eager"
        referrerpolicy="no-referrer"
      ></iframe>
    </section>

    <footer class="footer">
      Exported by Perchance Web Scraper. Extracted source is stored locally in <code>main.pjs</code>.
    </footer>
  </main>

  <script>
    const loader = document.getElementById("loader");
    window.addEventListener("load", () => loader.setAttribute("data-hidden", "true"), {{ once: true }});
    setTimeout(() => loader.setAttribute("data-hidden", "true"), 2600);
  </script>
</body>
</html>
"""


class ScrapeCancelled(Exception):
    pass


class PerchanceScraper:
    def __init__(self, timeout=DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def scrape_many(self, urls, output_dir, log, progress, should_cancel):
        output_dir = Path(output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        cleaned_urls = self._dedupe_urls(urls)
        total = len(cleaned_urls)
        results = []

        log(f"[info] Output directory: {output_dir}")
        log(f"[info] URL count after cleanup: {total}")

        for index, raw_url in enumerate(cleaned_urls, start=1):
            if should_cancel():
                raise ScrapeCancelled("Scrape cancelled by user.")

            url = self.normalize_url(raw_url)
            progress(index - 1, total, f"Preparing {index}/{total}")

            if not url:
                log(f"[skip] Invalid URL: {raw_url}")
                results.append({
                    "url": raw_url,
                    "status": "failed",
                    "reason": "invalid-url",
                })
                continue

            try:
                log(f"[fetch] ({index}/{total}) {url}")
                item = self.scrape_one(
                    url=url,
                    output_dir=output_dir,
                    log=log,
                    should_cancel=should_cancel,
                )
                results.append(item)
                log(f"[ok] Saved -> {item['folder']}")
            except ScrapeCancelled:
                raise
            except Exception as exc:
                log(f"[error] {url} -> {exc}")
                results.append({
                    "url": url,
                    "status": "failed",
                    "reason": str(exc),
                })

            progress(index, total, f"Processed {index}/{total}")
            time.sleep(REQUEST_DELAY)

        saved = sum(1 for r in results if r.get("status") == "saved")
        failed = sum(1 for r in results if r.get("status") == "failed")

        report = {
            "saved": saved,
            "failed": failed,
            "total": total,
            "results": results,
        }

        report_path = output_dir / "_scrape_report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        log(f"[report] Wrote {report_path.name}")

        return report

    def scrape_one(self, url, output_dir, log, should_cancel):
        if should_cancel():
            raise ScrapeCancelled("Cancelled before fetch.")

        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        final_url = response.url
        html_text = response.text

        title, raw_slug = self.get_page_identity(final_url, html_text)
        folder_name = self.make_unique_folder(output_dir, raw_slug)
        folder = output_dir / folder_name
        folder.mkdir(parents=True, exist_ok=True)

        extracted = self.extract_perchance_source(html_text)
        if not extracted["model_text"]:
            raise ValueError("Could not extract Perchance source from page")

        kind = self.detect_kind(final_url, title, extracted["imports"], extracted["strategy"])
        wrapper_html = self.build_wrapper(
            title=title,
            source_url=final_url,
            kind=kind,
        )

        pjs_path = folder / "main.pjs"
        html_path = folder / "index.html"
        meta_path = folder / "metadata.json"

        pjs_path.write_text(extracted["model_text"].rstrip() + "\n", encoding="utf-8")
        html_path.write_text(wrapper_html, encoding="utf-8")
        meta_path.write_text(
            json.dumps(
                {
                    "title": title,
                    "slug": folder_name,
                    "url": url,
                    "final_url": final_url,
                    "kind": kind,
                    "extraction_strategy": extracted["strategy"],
                    "imports": extracted["imports"],
                    "found_model_script": extracted["found_model_script"],
                    "found_preloaded_generator_data": extracted["found_preloaded_generator_data"],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        log(f"[save] {folder_name}/main.pjs")
        log(f"[save] {folder_name}/index.html")
        log(f"[save] {folder_name}/metadata.json")

        return {
            "url": url,
            "final_url": final_url,
            "title": title,
            "folder": str(folder),
            "status": "saved",
            "kind": kind,
            "extraction_strategy": extracted["strategy"],
        }

    def extract_perchance_source(self, html_text):
        soup = BeautifulSoup(html_text, "html.parser")

        result = {
            "model_text": None,
            "strategy": None,
            "imports": [],
            "found_model_script": False,
            "found_preloaded_generator_data": False,
        }

        model_script = soup.find("script", id="modelScript")
        if model_script is not None:
            result["found_model_script"] = True
            model_text = model_script.string if model_script.string is not None else model_script.get_text("", strip=False)
            if model_text and model_text.strip():
                result["model_text"] = model_text.strip()
                result["strategy"] = "script#modelScript"
                result["imports"] = self.extract_imports(result["model_text"])
                return result

        preloaded = soup.find("script", id="preloaded-generator-data")
        if preloaded is not None:
            result["found_preloaded_generator_data"] = True
            preloaded_text = preloaded.get_text("", strip=False).strip()
            decoded_json = self.try_parse_preloaded_generator_data(preloaded_text)
            if decoded_json and isinstance(decoded_json, dict):
                model_text = decoded_json.get("modelText")
                if isinstance(model_text, str) and model_text.strip():
                    result["model_text"] = model_text.strip()
                    result["strategy"] = "preloaded-generator-data.modelText"
                    result["imports"] = self.extract_imports(result["model_text"])
                    return result

        regex_model_script = re.search(
            r'<script[^>]*id=["\']modelScript["\'][^>]*>(.*?)</script>',
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if regex_model_script:
            model_text = html.unescape(regex_model_script.group(1)).strip()
            if model_text:
                result["found_model_script"] = True
                result["model_text"] = model_text
                result["strategy"] = "regex-script#modelScript"
                result["imports"] = self.extract_imports(result["model_text"])
                return result

        regex_preloaded = re.search(
            r'<script[^>]*id=["\']preloaded-generator-data["\'][^>]*>(.*?)</script>',
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if regex_preloaded:
            decoded_json = self.try_parse_preloaded_generator_data(regex_preloaded.group(1).strip())
            if decoded_json and isinstance(decoded_json, dict):
                model_text = decoded_json.get("modelText")
                if isinstance(model_text, str) and model_text.strip():
                    result["found_preloaded_generator_data"] = True
                    result["model_text"] = model_text.strip()
                    result["strategy"] = "regex-preloaded-generator-data.modelText"
                    result["imports"] = self.extract_imports(result["model_text"])
                    return result

        regex_generator_data = re.search(
            r'window\.generatorData\s*=\s*JSON\.parse\(\s*decodeURI\(\s*document\.querySelector\([^)]+\)\.innerText\s*\)\s*\)',
            html_text,
            flags=re.IGNORECASE,
        )
        if regex_generator_data and preloaded is not None:
            decoded_json = self.try_parse_preloaded_generator_data(preloaded.get_text("", strip=False).strip())
            if decoded_json and isinstance(decoded_json, dict):
                model_text = decoded_json.get("modelText")
                if isinstance(model_text, str) and model_text.strip():
                    result["model_text"] = model_text.strip()
                    result["strategy"] = "window.generatorData-from-preloaded-generator-data"
                    result["imports"] = self.extract_imports(result["model_text"])
                    return result

        return result

    def try_parse_preloaded_generator_data(self, raw_text):
        candidates = [
            raw_text,
            html.unescape(raw_text),
        ]

        for candidate in candidates:
            for decoder in (lambda s: s, unquote):
                try:
                    text = decoder(candidate).strip()
                    data = json.loads(text)
                    return data
                except Exception:
                    pass
        return None

    def extract_imports(self, model_text):
        imports = re.findall(r"\{import:([a-zA-Z0-9._\-]+)\}", model_text)
        return sorted(set(imports))

    def detect_kind(self, url, title, imports, strategy):
        joined = " ".join([url, title, " ".join(imports), strategy]).lower()
        if "plugin" in joined:
            return "plugin"
        return "generator"

    def get_page_identity(self, url, html_text):
        soup = BeautifulSoup(html_text, "html.parser")
        parsed = urlparse(url)

        slug_source = parsed.path.strip("/") or parsed.netloc.split(".")[0] or "perchance-item"
        slug_source = slug_source.split("/")[0]
        slug = self.slugify(slug_source)

        title = None

        static_meta = soup.find("script", id="static-meta-data")
        if static_meta:
            data = self.try_parse_preloaded_generator_data(static_meta.get_text("", strip=False).strip())
            if isinstance(data, dict):
                title = data.get("title") or title

        if not title:
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(" ", strip=True)

        if not title:
            title = slug.replace("-", " ").title()

        title = re.sub(r"\s+", " ", title).strip()
        return title, slug

    def build_wrapper(self, title, source_url, kind):
        kind_label = "Perchance Plugin Export" if kind == "plugin" else "Perchance Generator Export"
        return HTML_WRAPPER_TEMPLATE.format(
            title=html.escape(title),
            favicon=FAVICON_DATA_URI,
            kind_label=html.escape(kind_label),
            source_url=html.escape(source_url),
            iframe_url=html.escape(source_url, quote=True),
        )

    def make_unique_folder(self, base_dir, slug):
        slug = self.slugify(slug)
        candidate = slug
        index = 2
        while (base_dir / candidate).exists():
            candidate = f"{slug}-{index}"
            index += 1
        return candidate

    def normalize_url(self, raw):
        if not raw:
            return None

        value = raw.strip()
        if not value:
            return None

        if value.startswith("#"):
            return None

        if not re.match(r"^https?://", value, re.IGNORECASE):
            value = "https://" + value.lstrip("/")

        parsed = urlparse(value)
        if not parsed.netloc:
            return None

        if "perchance.org" not in parsed.netloc.lower():
            return None

        value = value.split("#", 1)[0].strip()
        return value

    def slugify(self, value):
        value = value.strip().lower()
        value = re.sub(r"[^a-z0-9._-]+", "-", value)
        value = re.sub(r"-{2,}", "-", value).strip("-._")
        return value or "perchance-item"

    def _dedupe_urls(self, urls):
        seen = set()
        cleaned = []
        for item in urls:
            normalized = self.normalize_url(item) if item else None
            key = normalized or (item.strip() if item else "")
            if key and key not in seen:
                seen.add(key)
                cleaned.append(item)
        return cleaned


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=14)
        self.master = master
        self.scraper = PerchanceScraper()
        self.log_queue = queue.Queue()
        self.cancel_requested = False
        self.worker_thread = None

        self.output_dir = tk.StringVar(value=str(Path.cwd() / "perchance_exports"))
        self.status_var = tk.StringVar(value="Idle")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._configure_window()
        self._build_ui()
        self._poll_queue()

    def _configure_window(self):
        self.master.title(APP_TITLE)
        self.master.geometry(APP_SIZE)
        self.master.minsize(980, 760)
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)

        self.grid(sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        style = ttk.Style(self.master)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

    def _build_ui(self):
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)

        ttk.Label(
            header,
            text="Perchance Generator / Plugin Scraper",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            header,
            text=(
                "Paste one Perchance generator or plugin URL per line. "
                "The scraper extracts Perchance source and saves main.pjs, index.html, and metadata.json."
            ),
            wraplength=1020,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        url_frame = ttk.LabelFrame(self, text="URL Input", padding=12)
        url_frame.grid(row=1, column=0, sticky="nsew")
        url_frame.columnconfigure(0, weight=1)
        url_frame.rowconfigure(0, weight=1)

        self.url_text = tk.Text(
            url_frame,
            height=13,
            wrap="word",
            undo=True,
            font=("Consolas", 10),
        )
        self.url_text.grid(row=0, column=0, sticky="nsew")

        url_scroll = ttk.Scrollbar(url_frame, orient="vertical", command=self.url_text.yview)
        url_scroll.grid(row=0, column=1, sticky="ns")
        self.url_text.configure(yscrollcommand=url_scroll.set)

        output_frame = ttk.LabelFrame(self, text="Output and Actions", padding=12)
        output_frame.grid(row=2, column=0, sticky="ew", pady=10)
        output_frame.columnconfigure(1, weight=1)

        ttk.Label(output_frame, text="Output folder").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(output_frame, textvariable=self.output_dir).grid(row=0, column=1, sticky="ew")
        ttk.Button(output_frame, text="Browse...", command=self.choose_output_dir).grid(row=0, column=2, padx=(8, 0))

        action_bar = ttk.Frame(output_frame)
        action_bar.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        action_bar.columnconfigure(8, weight=1)

        self.scrape_button = ttk.Button(action_bar, text="Scrape URLs", command=self.start_scrape)
        self.scrape_button.grid(row=0, column=0, padx=(0, 8))

        self.cancel_button = ttk.Button(action_bar, text="Cancel", command=self.cancel_scrape, state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=(0, 8))

        ttk.Button(action_bar, text="Import URLs from .txt", command=self.import_urls_from_file).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(action_bar, text="Load Example URLs", command=self.load_examples).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(action_bar, text="Clear URLs", command=self.clear_urls).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(action_bar, text="Open Output Folder", command=self.open_output_folder).grid(row=0, column=5, padx=(0, 8))
        ttk.Button(action_bar, text="Copy Log", command=self.copy_log).grid(row=0, column=6)

        ttk.Label(action_bar, textvariable=self.status_var).grid(row=0, column=9, sticky="e")

        self.progress = ttk.Progressbar(
            output_frame,
            mode="determinate",
            variable=self.progress_var,
            maximum=100,
        )
        self.progress.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0))

        log_frame = ttk.LabelFrame(self, text="Log Console", padding=12)
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=22,
            wrap="word",
            state="disabled",
            font=("Consolas", 10),
            background="#0f172a",
            foreground="#e5e7eb",
            insertbackground="#ffffff",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def choose_output_dir(self):
        path = filedialog.askdirectory(initialdir=self.output_dir.get() or str(Path.cwd()))
        if path:
            self.output_dir.set(path)

    def import_urls_from_file(self):
        path = filedialog.askopenfilename(
            title="Select URL text file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            content = Path(path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = Path(path).read_text(encoding="utf-8", errors="replace")

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        existing = self.url_text.get("1.0", tk.END).strip()
        joined = "\n".join(lines)

        if existing:
            self.url_text.insert(tk.END, ("\n" if not existing.endswith("\n") else "") + joined)
        else:
            self.url_text.insert("1.0", joined)

        self._log(f"[import] Loaded {len(lines)} line(s) from {path}")

    def load_examples(self):
        examples = "\n".join([
            "https://perchance.org/ai-character-chat",
            "https://perchance.org/text-adventure-generator",
            "https://perchance.org/upload-plugin",
            "https://perchance.org/importable-instance-plugin",
        ])
        self.url_text.delete("1.0", tk.END)
        self.url_text.insert("1.0", examples)
        self._log("[info] Example URLs loaded.")

    def clear_urls(self):
        self.url_text.delete("1.0", tk.END)

    def open_output_folder(self):
        path = Path(self.output_dir.get()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        try:
            import os
            os.startfile(path)
        except Exception:
            messagebox.showinfo(APP_TITLE, f"Output folder:\n{path}")

    def copy_log(self):
        text = self.log_text.get("1.0", tk.END).strip()
        self.master.clipboard_clear()
        self.master.clipboard_append(text)
        self.master.update_idletasks()
        self._log("[info] Log copied to clipboard.")

    def start_scrape(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning(APP_TITLE, "A scrape is already running.")
            return

        urls = [line.strip() for line in self.url_text.get("1.0", tk.END).splitlines() if line.strip()]
        if not urls:
            messagebox.showwarning(APP_TITLE, "Paste at least one URL.")
            return

        output_dir = self.output_dir.get().strip()
        if not output_dir:
            messagebox.showwarning(APP_TITLE, "Choose an output folder.")
            return

        self.cancel_requested = False
        self.scrape_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress_var.set(0)
        self.status_var.set("Scraping...")
        self._log(f"[start] Starting scrape for {len(urls)} URL(s).")

        self.worker_thread = threading.Thread(
            target=self._worker_scrape,
            args=(urls, output_dir),
            daemon=True,
        )
        self.worker_thread.start()

    def cancel_scrape(self):
        self.cancel_requested = True
        self.status_var.set("Cancelling...")
        self._log("[info] Cancel requested...")

    def _worker_scrape(self, urls, output_dir):
        try:
            report = self.scraper.scrape_many(
                urls=urls,
                output_dir=output_dir,
                log=self._queue_log,
                progress=self._queue_progress,
                should_cancel=lambda: self.cancel_requested,
            )
            self.log_queue.put(("done", report))
        except ScrapeCancelled as exc:
            self.log_queue.put(("cancelled", str(exc)))
        except Exception as exc:
            self.log_queue.put(("fatal", str(exc)))

    def _queue_log(self, message):
        self.log_queue.put(("log", message))

    def _queue_progress(self, current, total, status_text):
        self.log_queue.put(("progress", (current, total, status_text)))

    def _poll_queue(self):
        try:
            while True:
                event_type, payload = self.log_queue.get_nowait()

                if event_type == "log":
                    self._log(payload)

                elif event_type == "progress":
                    current, total, status_text = payload
                    percent = 0 if total <= 0 else (current / total) * 100
                    self.progress_var.set(percent)
                    self.status_var.set(status_text)

                elif event_type == "done":
                    self.progress_var.set(100)
                    self.status_var.set(
                        f"Complete: {payload['saved']} saved, {payload['failed']} failed"
                    )
                    self.scrape_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    self._log(
                        f"[done] Saved: {payload['saved']} | Failed: {payload['failed']} | Total: {payload['total']}"
                    )
                    messagebox.showinfo(
                        APP_TITLE,
                        f"Finished.\n\nSaved: {payload['saved']}\nFailed: {payload['failed']}\nTotal: {payload['total']}"
                    )

                elif event_type == "cancelled":
                    self.scrape_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    self.status_var.set("Cancelled")
                    self._log(f"[cancelled] {payload}")
                    messagebox.showinfo(APP_TITLE, payload)

                elif event_type == "fatal":
                    self.scrape_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    self.status_var.set("Failed")
                    self._log(f"[fatal] {payload}")
                    messagebox.showerror(APP_TITLE, payload)

        except queue.Empty:
            pass

        self.after(100, self._poll_queue)

    def _log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()