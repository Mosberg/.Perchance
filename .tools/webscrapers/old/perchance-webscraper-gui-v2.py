#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import queue
import re
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse, urlunparse

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
    "%3Crect width='64' height='64' rx='14' fill='%23111727'/%3E"
    "%3Cpath d='M18 14h17c8 0 13 4 13 11 0 5-2 8-7 10 6 2 9 6 9 13 0 10-7 16-19 16H18V14zm11 8v10h6c4 0 6-2 6-5s-2-5-6-5h-6zm0 18v12h8c4 0 7-2 7-6s-3-6-8-6h-7z' fill='white'/%3E"
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
      --bg: #0f172a;
      --panel: rgba(15, 23, 42, 0.88);
      --text: #f8fafc;
      --muted: #94a3b8;
      --accent: #22c55e;
      --border: rgba(255,255,255,0.08);
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; margin: 0; }}
    body {{
      font-family: Inter, Segoe UI, Arial, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top, rgba(34, 197, 94, 0.18), transparent 40%),
        linear-gradient(180deg, #020617 0%, #0f172a 100%);
      display: grid;
      place-items: center;
      padding: 18px;
    }}
    .app {{
      width: min(1100px, 96vw);
      height: min(860px, 92vh);
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 24px 80px rgba(0,0,0,0.35);
      display: grid;
      grid-template-rows: auto 1fr;
      backdrop-filter: blur(12px);
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      padding: 14px 18px;
      border-bottom: 1px solid var(--border);
    }}
    .title {{
      font-size: 1rem;
      font-weight: 700;
      letter-spacing: 0.02em;
    }}
    .meta {{
      color: var(--muted);
      font-size: 0.875rem;
      text-align: right;
    }}
    .frame {{
      position: relative;
      min-height: 0;
    }}
    iframe {{
      width: 100%;
      height: 100%;
      border: 0;
      background: #fff;
    }}
    .loader {{
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      background: rgba(2, 6, 23, 0.78);
      z-index: 5;
      transition: opacity 180ms ease;
    }}
    .loader[data-hidden="true"] {{
      opacity: 0;
      pointer-events: none;
    }}
    .loader__box {{
      text-align: center;
      padding: 24px 28px;
    }}
    .spinner {{
      width: 44px;
      height: 44px;
      margin: 0 auto 12px;
      border-radius: 999px;
      border: 3px solid rgba(255,255,255,0.15);
      border-top-color: var(--accent);
      animation: spin 0.9s linear infinite;
    }}
    .loader__title {{
      font-weight: 700;
      margin-bottom: 6px;
    }}
    .loader__text {{
      color: var(--muted);
      font-size: 0.9375rem;
    }}
    @keyframes spin {{
      to {{ transform: rotate(360deg); }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <div class="topbar">
      <div class="title">{title}</div>
      <div class="meta">Saved from {source_url}</div>
    </div>
    <div class="frame">
      <div class="loader" id="loader" aria-live="polite">
        <div class="loader__box">
          <div class="spinner" aria-hidden="true"></div>
          <div class="loader__title">Loading saved Perchance wrapper</div>
          <div class="loader__text">Opening the original generator in an embedded preview.</div>
        </div>
      </div>
      <iframe src="{escaped_url}" title="{title}" loading="eager"></iframe>
    </div>
  </div>
  <script>
    const loader = document.getElementById("loader");
    window.addEventListener("load", () => {{
      loader.setAttribute("data-hidden", "true");
    }}, {{ once: true }});
    setTimeout(() => {{
      loader.setAttribute("data-hidden", "true");
    }}, 3000);
  </script>
</body>
</html>
"""


@dataclass
class ScrapeResult:
    input_url: str
    normalized_url: str
    folder: Path
    main_pjs: Path
    index_html: Path
    metadata_json: Path
    title: str
    slug: str


class CancelledError(Exception):
    pass


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise CancelledError("Scrape cancelled by user.")


class PerchanceScraper:
    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": "https://perchance.org/",
            "Upgrade-Insecure-Requests": "1",
        })

    def scrape_many(self, urls, output_dir, logger, progress, cancel_token: CancelToken):
        output_dir = Path(output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        cleaned_urls = [u.strip() for u in urls if u and u.strip()]
        total = len(cleaned_urls)
        saved = 0
        failed = 0
        cancelled = False
        results = []

        for index, raw_url in enumerate(cleaned_urls, start=1):
            cancel_token.raise_if_cancelled()
            progress(index - 1, total, f"Preparing {raw_url}")

            try:
                normalized_url = self.normalize_url(raw_url)
                if not normalized_url:
                    raise ValueError("Invalid URL")

                logger(f"[NORMALIZE] {raw_url} -> {normalized_url}")
                progress(index - 1, total, f"Fetching {normalized_url}")

                result = self.scrape_one(
                    input_url=raw_url,
                    normalized_url=normalized_url,
                    output_dir=output_dir,
                    logger=logger,
                    cancel_token=cancel_token,
                )
                results.append(result)
                saved += 1
                logger(f"[SUCCESS] Saved: {result.folder}")
            except CancelledError:
                cancelled = True
                logger("[CANCELLED] Stopped by user.")
                break
            except Exception as exc:
                failed += 1
                logger(f"[ERROR] {raw_url} -> {exc}")

            progress(index, total, f"Processed {index}/{total}")

        return {
            "total": total,
            "saved": saved,
            "failed": failed,
            "cancelled": cancelled,
            "results": results,
            "output_dir": output_dir,
        }

    def scrape_one(self, input_url: str, normalized_url: str, output_dir: Path, logger, cancel_token: CancelToken) -> ScrapeResult:
        cancel_token.raise_if_cancelled()
        response = self.fetch_page(normalized_url, cancel_token, logger)
        cancel_token.raise_if_cancelled()

        html_text = response.text
        title, slug = self.get_page_identity(normalized_url, html_text)

        folder = output_dir / slug
        folder.mkdir(parents=True, exist_ok=True)

        main_code = self.extract_model_script(html_text)
        if not main_code:
            raise ValueError('Could not find <script id="modelScript"> content')

        main_pjs = folder / "main.pjs"
        index_html = folder / "index.html"
        metadata_json = folder / "metadata.json"
        raw_snapshot = folder / "page_snapshot.html"

        metadata = {
            "input_url": input_url,
            "normalized_url": normalized_url,
            "final_url": response.url,
            "title": title,
            "slug": slug,
            "saved_at_unix": int(time.time()),
        }

        main_pjs.write_text(main_code, encoding="utf-8")
        index_html.write_text(self.build_wrapper(title=title, source_url=normalized_url), encoding="utf-8")
        metadata_json.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        raw_snapshot.write_text(html_text, encoding="utf-8")

        logger(f"[SAVE] {main_pjs.name}, {index_html.name}, {metadata_json.name}, {raw_snapshot.name}")

        return ScrapeResult(
            input_url=input_url,
            normalized_url=normalized_url,
            folder=folder,
            main_pjs=main_pjs,
            index_html=index_html,
            metadata_json=metadata_json,
            title=title,
            slug=slug,
        )

    def fetch_page(self, url: str, cancel_token: CancelToken, logger):
        cancel_token.raise_if_cancelled()

        response = self.session.get(url, timeout=self.timeout)
        if response.status_code == 403:
            logger("[WARN] First request returned 403, retrying with fetch headers...")
            retry_headers = {
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
            }
            response = self.session.get(url, timeout=self.timeout, headers=retry_headers)

        response.raise_for_status()
        return response

    def extract_model_script(self, html_text: str) -> str | None:
        soup = BeautifulSoup(html_text, "html.parser")
        node = soup.find("script", id="modelScript")

        if node and node.string is not None:
            text = node.string.strip()
            return text + "\n" if text else None

        if node:
            text = node.get_text("", strip=False).strip()
            return text + "\n" if text else None

        match = re.search(
            r'<script[^>]*id=["\']modelScript["\'][^>]*>(.*?)</script>',
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            text = html.unescape(match.group(1)).strip()
            return text + "\n" if text else None

        return None

    def get_page_identity(self, url: str, html_text: str) -> tuple[str, str]:
        parsed = urlparse(url)
        raw_slug = parsed.path.strip("/") or parsed.netloc.split(".")[0] or "perchance-item"
        raw_slug = raw_slug.split("/")[0]
        slug = self.slugify(raw_slug)

        soup = BeautifulSoup(html_text, "html.parser")
        title_node = soup.find("title")
        title = title_node.get_text(" ", strip=True) if title_node else slug.replace("-", " ").title()
        return title, slug

    def build_wrapper(self, title: str, source_url: str) -> str:
        return WRAPPER_TEMPLATE.format(
            title=html.escape(title),
            source_url=html.escape(source_url),
            escaped_url=html.escape(source_url, quote=True),
            favicon=FAVICON_DATA_URI,
        )

    @staticmethod
    def normalize_url(raw: str) -> str | None:
        if not raw:
            return None

        candidate = raw.strip()
        if not candidate:
            return None

        md_match = re.match(r"^\[.*?\]\((https?://[^)]+)\)$", candidate, flags=re.IGNORECASE)
        if md_match:
            candidate = md_match.group(1)

        if not re.match(r"^https?://", candidate, flags=re.IGNORECASE):
            candidate = "https://" + candidate.lstrip("/")

        parsed = urlparse(candidate)
        if not parsed.netloc:
            return None

        cleaned = parsed._replace(fragment="")
        return urlunparse(cleaned)

    @staticmethod
    def slugify(value: str) -> str:
        value = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
        value = re.sub(r"-+", "-", value).strip("-._")
        return value or "perchance-item"


class PerchanceScraperApp(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=14)
        self.master = master
        self.scraper = PerchanceScraper()
        self.log_queue: queue.Queue = queue.Queue()
        self.cancel_token: CancelToken | None = None
        self.worker_thread: threading.Thread | None = None

        self.output_dir_var = tk.StringVar(value=str(Path.cwd() / "perchance_exports"))
        self.status_var = tk.StringVar(value="Idle")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build_ui()
        self._poll_queue()

    def _build_ui(self) -> None:
        self.master.title(APP_TITLE)
        self.master.geometry("1100x820")
        self.master.minsize(960, 700)

        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(5, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)

        ttk.Label(
            header,
            text="Perchance Generator / Plugin Web Scraper",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            header,
            text=(
                "Paste one URL per line, import a .txt file, or mix generator/plugin URLs. "
                "The app strips #edit, fetches the public page, extracts modelScript, "
                "and saves main.pjs + index.html + metadata.json."
            ),
            wraplength=980,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        input_frame = ttk.LabelFrame(self, text="Perchance URLs", padding=12)
        input_frame.grid(row=1, column=0, sticky="nsew")
        input_frame.columnconfigure(0, weight=1)
        input_frame.rowconfigure(0, weight=1)

        self.url_text = tk.Text(self, height=14, wrap="word", undo=True)
        self.url_text = tk.Text(input_frame, height=14, wrap="word", undo=True)
        self.url_text.grid(row=0, column=0, sticky="nsew")

        url_scroll = ttk.Scrollbar(input_frame, orient="vertical", command=self.url_text.yview)
        url_scroll.grid(row=0, column=1, sticky="ns")
        self.url_text.configure(yscrollcommand=url_scroll.set)

        file_frame = ttk.LabelFrame(self, text="Output", padding=12)
        file_frame.grid(row=2, column=0, sticky="ew", pady=12)
        file_frame.columnconfigure(1, weight=1)

        ttk.Label(file_frame, text="Folder").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(file_frame, textvariable=self.output_dir_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(file_frame, text="Browse...", command=self.choose_output_dir).grid(row=0, column=2, padx=(8, 0))

        actions = ttk.Frame(self)
        actions.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        for i in range(8):
            actions.columnconfigure(i, weight=0)
        actions.columnconfigure(8, weight=1)

        self.scrape_button = ttk.Button(actions, text="Scrape", command=self.start_scrape)
        self.scrape_button.grid(row=0, column=0, padx=(0, 8))

        self.cancel_button = ttk.Button(actions, text="Cancel", command=self.cancel_scrape, state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=(0, 8))

        ttk.Button(actions, text="Import URLs from .txt", command=self.import_urls_from_text).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(actions, text="Load Examples", command=self.load_examples).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(actions, text="Clear URLs", command=self.clear_urls).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(actions, text="Open Output Folder", command=self.open_output_folder).grid(row=0, column=5)

        ttk.Label(actions, textvariable=self.status_var).grid(row=0, column=8, sticky="e")

        progress_frame = ttk.LabelFrame(self, text="Progress", padding=12)
        progress_frame.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        progress_frame.columnconfigure(0, weight=1)

        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate", maximum=100, variable=self.progress_var)
        self.progress_bar.grid(row=0, column=0, sticky="ew")

        self.progress_label = ttk.Label(progress_frame, text="Waiting to start.")
        self.progress_label.grid(row=1, column=0, sticky="w", pady=(8, 0))

        log_frame = ttk.LabelFrame(self, text="Log", padding=12)
        log_frame.grid(row=5, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            wrap="word",
            state="disabled",
            background="#0f172a",
            foreground="#f8fafc",
            insertbackground="#f8fafc",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def choose_output_dir(self) -> None:
        path = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(Path.cwd()))
        if path:
            self.output_dir_var.set(path)

    def import_urls_from_text(self) -> None:
        path = filedialog.askopenfilename(
            title="Select text file with URLs",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not path:
            return

        try:
            content = Path(path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = Path(path).read_text(encoding="utf-8", errors="replace")

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            messagebox.showwarning(APP_TITLE, "The selected file did not contain any non-empty lines.")
            return

        current = self.url_text.get("1.0", tk.END).strip()
        joined = "\n".join(lines)
        if current:
            self.url_text.insert(tk.END, "\n" + joined)
        else:
            self.url_text.insert("1.0", joined)

        self._log(f"[IMPORT] Loaded {len(lines)} URL line(s) from {path}")

    def load_examples(self) -> None:
        example_urls = "\n".join([
            "https://perchance.org/minimal#edit",
            "https://perchance.org/text-to-image-plugin#edit",
            "https://perchance.org/ai-character-chat",
        ])
        self.url_text.delete("1.0", tk.END)
        self.url_text.insert("1.0", example_urls)

    def clear_urls(self) -> None:
        self.url_text.delete("1.0", tk.END)

    def open_output_folder(self) -> None:
        path = Path(self.output_dir_var.get()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        try:
            import os
            os.startfile(path)
        except Exception:
            messagebox.showinfo("Output Folder", str(path))

    def start_scrape(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning(APP_TITLE, "A scrape is already running.")
            return

        urls = [line.strip() for line in self.url_text.get("1.0", tk.END).splitlines() if line.strip()]
        if not urls:
            messagebox.showwarning(APP_TITLE, "Paste or import at least one URL.")
            return

        out_dir = self.output_dir_var.get().strip()
        if not out_dir:
            messagebox.showwarning(APP_TITLE, "Choose an output folder.")
            return

        self.cancel_token = CancelToken()
        self.scrape_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status_var.set("Scraping...")
        self.progress_var.set(0)
        self.progress_label.configure(text=f"Starting {len(urls)} URL(s)...")
        self._log(f"[START] Starting scrape for {len(urls)} URL(s)")

        self.worker_thread = threading.Thread(
            target=self._run_scrape,
            args=(urls, out_dir, self.cancel_token),
            daemon=True,
        )
        self.worker_thread.start()

    def cancel_scrape(self) -> None:
        if self.cancel_token:
            self.cancel_token.cancel()
            self.status_var.set("Cancelling...")
            self.progress_label.configure(text="Cancellation requested...")
            self._log("[CANCEL] Cancellation requested by user.")

    def _run_scrape(self, urls, out_dir, cancel_token: CancelToken) -> None:
        def logger(message: str) -> None:
            self.log_queue.put(("log", message))

        def progress(done: int, total: int, text: str) -> None:
            percent = 0 if total == 0 else (done / total) * 100
            self.log_queue.put(("progress", {"done": done, "total": total, "percent": percent, "text": text}))

        try:
            summary = self.scraper.scrape_many(
                urls=urls,
                output_dir=out_dir,
                logger=logger,
                progress=progress,
                cancel_token=cancel_token,
            )
            self.log_queue.put(("done", summary))
        except Exception as exc:
            self.log_queue.put(("fatal", str(exc)))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()

                if kind == "log":
                    self._log(payload)

                elif kind == "progress":
                    self.progress_var.set(payload["percent"])
                    self.progress_label.configure(text=payload["text"])

                elif kind == "done":
                    self.scrape_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")

                    total = payload["total"]
                    saved = payload["saved"]
                    failed = payload["failed"]
                    cancelled = payload["cancelled"]

                    if cancelled:
                        self.status_var.set(f"Cancelled: {saved} saved, {failed} failed")
                        self.progress_label.configure(text="Scrape cancelled.")
                        self._log("[END] Scrape cancelled.")
                        messagebox.showinfo(APP_TITLE, f"Cancelled.\nSaved: {saved}\nFailed: {failed}\nTotal queued: {total}")
                    else:
                        self.progress_var.set(100 if total else 0)
                        self.status_var.set(f"Complete: {saved} saved, {failed} failed")
                        self.progress_label.configure(text="Finished.")
                        self._log("[END] Scrape finished.")
                        messagebox.showinfo(APP_TITLE, f"Finished.\nSaved: {saved}\nFailed: {failed}\nTotal queued: {total}")

                elif kind == "fatal":
                    self.scrape_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    self.status_var.set("Failed")
                    self.progress_label.configure(text="Fatal error.")
                    self._log(f"[FATAL] {payload}")
                    messagebox.showerror(APP_TITLE, payload)

        except queue.Empty:
            pass

        self.after(120, self._poll_queue)

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    PerchanceScraperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()