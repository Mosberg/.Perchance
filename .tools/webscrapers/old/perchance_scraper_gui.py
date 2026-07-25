#!/usr/bin/env python3
import json
import queue
import random
import re
import socket
import threading
import time
import tkinter as tk
from dataclasses import dataclass, asdict
from html import unescape
from ipaddress import ip_address, ip_network
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

APP_TITLE = "Perchance Source Scraper"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
PRIVATE_NETWORKS = [
    ip_network("127.0.0.0/8"),
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("169.254.0.0/16"),
    ip_network("::1/128"),
    ip_network("fc00::/7"),
    ip_network("fe80::/10"),
]


@dataclass
class ScraperSettings:
    timeout_seconds: int = 30
    delay_min_seconds: float = 1.5
    delay_max_seconds: float = 3.5
    max_retries: int = 3
    allow_off_domain: bool = False
    respect_robots_txt: bool = True
    save_raw_html: bool = False
    save_manifest: bool = True
    save_debug_json: bool = True
    overwrite_existing: bool = True
    max_response_bytes: int = 8_000_000


class LoggerMixin:
    def __init__(self, log_func):
        self.log = log_func


class RobotsPolicy(LoggerMixin):
    def __init__(self, user_agent, timeout, log_func):
        super().__init__(log_func)
        self.user_agent = user_agent
        self.timeout = timeout
        self.cache = {}

    def can_fetch(self, url):
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        if robots_url not in self.cache:
            rp = RobotFileParser()
            rp.set_url(robots_url)
            try:
                rp.read()
                self.cache[robots_url] = rp
                self.log(f"[robots] Loaded {robots_url}")
            except Exception as exc:
                self.log(f"[robots] Could not load {robots_url}: {exc}. Falling back to allow.")
                self.cache[robots_url] = None
        parser = self.cache[robots_url]
        if parser is None:
            return True
        allowed = parser.can_fetch(self.user_agent, url)
        self.log(f"[robots] {'allow' if allowed else 'deny'} {url}")
        return allowed


class DomainRateLimiter(LoggerMixin):
    def __init__(self, settings, log_func):
        super().__init__(log_func)
        self.settings = settings
        self.last_request_at = {}

    def wait(self, url):
        host = urlparse(url).netloc.lower()
        now = time.monotonic()
        last = self.last_request_at.get(host)
        target_delay = random.uniform(self.settings.delay_min_seconds, self.settings.delay_max_seconds)
        if last is not None:
            elapsed = now - last
            remaining = target_delay - elapsed
            if remaining > 0:
                self.log(f"[throttle] Waiting {remaining:.2f}s for {host}")
                time.sleep(remaining)
        self.last_request_at[host] = time.monotonic()


class SafeUrlValidator:
    @staticmethod
    def normalize(url):
        value = (url or "").strip()
        if not value:
            return None
        if not re.match(r"^https?://", value, re.I):
            value = "https://" + value.lstrip("/")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        return value

    @staticmethod
    def validate_target(url, allow_off_domain=False):
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not allow_off_domain and not (host == "perchance.org" or host.endswith(".perchance.org")):
            raise ValueError("Only perchance.org domains are allowed unless off-domain scraping is enabled.")
        if host in {"localhost"}:
            raise ValueError("Blocked localhost target.")
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise ValueError(f"DNS resolution failed: {exc}") from exc
        for info in infos:
            ip = ip_address(info[4][0])
            if any(ip in net for net in PRIVATE_NETWORKS):
                raise ValueError(f"Blocked private/internal target: {ip}")


class PerchanceExtractor:
    def __init__(self, log_func):
        self.log = log_func

    def extract(self, raw_html):
        soup = BeautifulSoup(raw_html, "html.parser")
        model_text, model_source = self._extract_model_text(soup, raw_html)
        output_template, output_source = self._extract_output_template(soup, raw_html)
        model_script, model_script_source = self._extract_model_script(soup, raw_html)

        if not model_text and model_script:
            model_text = model_script
            model_source = f"fallback:{model_script_source}"

        result = {
            "main.pjs": model_text,
            "index.html": output_template,
            "debug": {
                "model_source": model_source,
                "html_source": output_source,
                "model_script_source": model_script_source,
                "has_model_text": bool(model_text),
                "has_output_template": bool(output_template),
            },
        }
        return result

    def _extract_model_script(self, soup, raw_html):
        node = soup.find("script", id="modelScript")
        if node:
            if node.string is not None:
                return node.string.strip() + "\n", "script#modelScript.string"
            if node.contents:
                return "".join(str(x) for x in node.contents).strip() + "\n", "script#modelScript.contents"
        m = re.search(r'<script[^>]*id=["\']modelScript["\'][^>]*>(.*?)</script>', raw_html, re.I | re.S)
        if m:
            return unescape(m.group(1)).strip() + "\n", "regex:modelScript"
        return None, None

    def _extract_model_text(self, soup, raw_html):
        candidates = []
        for tag in soup.find_all("textarea"):
            text = tag.get_text("", strip=False)
            if self._looks_like_pjs_source(text):
                candidates.append((text, "textarea"))
        for tag in soup.find_all("input"):
            value = tag.get("value")
            if self._looks_like_pjs_source(value):
                candidates.append((value, "input[value]"))
        for script in soup.find_all("script"):
            script_text = script.string if script.string is not None else script.get_text("", strip=False)
            if not script_text:
                continue
            for key in ("modelTextInitialContent", "modelText"):
                found = self._extract_assignment(script_text, key)
                if self._looks_like_pjs_source(found):
                    candidates.append((found, f"script:{key}"))
        for pattern, label in [
            (r'modelTextInitialContent\s*=\s*([\'"`])(?P<val>.*?)(?<!\\)\1', "regex:modelTextInitialContent"),
            (r'modelText\s*:\s*([\'"`])(?P<val>.*?)(?<!\\)\1', "regex:modelTextObject"),
            (r'"modelText"\s*:\s*"(?P<val>(?:\\.|[^"])*)"', "regex:modelTextJson"),
        ]:
            for match in re.finditer(pattern, raw_html, re.I | re.S):
                val = self._decode_js_string(match.group("val"))
                if self._looks_like_pjs_source(val):
                    candidates.append((val, label))
        return self._pick_best(candidates)

    def _extract_output_template(self, soup, raw_html):
        candidates = []
        for tag in soup.find_all("template"):
            value = tag.get_text("", strip=False)
            if self._looks_like_html_source(value):
                candidates.append((value, "template"))
        for tag in soup.find_all("textarea"):
            value = tag.get_text("", strip=False)
            if self._looks_like_html_source(value):
                candidates.append((value, "textarea"))
        for tag in soup.find_all("input"):
            value = tag.get("value")
            if self._looks_like_html_source(value):
                candidates.append((value, "input[value]"))
        for script in soup.find_all("script"):
            script_text = script.string if script.string is not None else script.get_text("", strip=False)
            if not script_text:
                continue
            for key in ("outputTemplateInitialContent", "outputTemplate"):
                found = self._extract_assignment(script_text, key)
                if self._looks_like_html_source(found):
                    candidates.append((found, f"script:{key}"))
        for pattern, label in [
            (r'outputTemplateInitialContent\s*=\s*([\'"`])(?P<val>.*?)(?<!\\)\1', "regex:outputTemplateInitialContent"),
            (r'outputTemplate\s*:\s*([\'"`])(?P<val>.*?)(?<!\\)\1', "regex:outputTemplateObject"),
            (r'"outputTemplate"\s*:\s*"(?P<val>(?:\\.|[^"])*)"', "regex:outputTemplateJson"),
        ]:
            for match in re.finditer(pattern, raw_html, re.I | re.S):
                val = self._decode_js_string(match.group("val"))
                if self._looks_like_html_source(val):
                    candidates.append((val, label))
        return self._pick_best(candidates)

    def _extract_assignment(self, script_text, key):
        patterns = [
            rf'{re.escape(key)}\s*[:=]\s*([\'"`])(?P<val>.*?)(?<!\\)\1',
            rf'"{re.escape(key)}"\s*:\s*"(?P<val>(?:\\.|[^"])*)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, script_text, re.I | re.S)
            if match:
                return self._decode_js_string(match.group("val"))
        return None

    def _decode_js_string(self, value):
        if value is None:
            return None
        try:
            return bytes(value, "utf-8").decode("unicode_escape")
        except Exception:
            return value

    def _looks_like_pjs_source(self, text):
        if not text or len(text.strip()) < 8:
            return False
        sample = text.strip()
        signals = ["[", "=", "\\n", "import", "output"]
        return sum(1 for s in signals if s in sample) >= 2

    def _looks_like_html_source(self, text):
        if not text or len(text.strip()) < 12:
            return False
        sample = text.strip().lower()
        signals = ["<div", "<span", "<p", "<style", "<script", "<!doctype", "<html", "</"]
        return any(sig in sample for sig in signals)

    def _pick_best(self, candidates):
        filtered = [(c.strip() + "\n", src) for c, src in candidates if c and c.strip()]
        if not filtered:
            return None, None
        filtered.sort(key=lambda item: len(item[0]), reverse=True)
        return filtered[0]


class PerchanceScraper(LoggerMixin):
    def __init__(self, settings, log_func):
        super().__init__(log_func)
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        self.extractor = PerchanceExtractor(log_func)
        self.rate_limiter = DomainRateLimiter(settings, log_func)
        self.robots = RobotsPolicy(USER_AGENT, settings.timeout_seconds, log_func)

    def scrape_many(self, urls, output_dir):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        summary = {"saved": 0, "failed": 0, "skipped": 0, "items": []}
        seen = set()

        for raw in urls:
            normalized = SafeUrlValidator.normalize(raw)
            if not normalized:
                self.log(f"[skip] Invalid URL: {raw}")
                summary["skipped"] += 1
                continue
            if normalized in seen:
                self.log(f"[skip] Duplicate URL: {normalized}")
                summary["skipped"] += 1
                continue
            seen.add(normalized)

            try:
                SafeUrlValidator.validate_target(normalized, self.settings.allow_off_domain)
                if self.settings.respect_robots_txt and not self.robots.can_fetch(normalized):
                    raise ValueError("Blocked by robots.txt")
                result = self.scrape_one(normalized, output_dir)
                summary["saved"] += 1
                summary["items"].append(result)
            except Exception as exc:
                self.log(f"[error] {normalized} -> {exc}")
                summary["failed"] += 1

        if self.settings.save_manifest:
            manifest_path = output_dir / "manifest.json"
            manifest_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
            self.log(f"[save] {manifest_path}")
        return summary

    def scrape_one(self, url, output_dir):
        self.rate_limiter.wait(url)
        html_text = self._fetch_with_retries(url)
        extracted = self.extractor.extract(html_text)

        if not extracted["main.pjs"]:
            raise ValueError("Could not extract modelText/main.pjs")
        if not extracted["index.html"]:
            raise ValueError("Could not extract outputTemplate/index.html")

        slug = self._slugify((urlparse(url).path.strip("/") or "perchance-item").split("/")[0])
        folder = output_dir / slug
        folder.mkdir(parents=True, exist_ok=True)

        pjs_path = folder / "main.pjs"
        html_path = folder / "index.html"
        metadata_path = folder / "metadata.json"
        debug_path = folder / "debug.json"
        raw_html_path = folder / "source.html"

        if not self.settings.overwrite_existing and (pjs_path.exists() or html_path.exists()):
            raise FileExistsError(f"Refusing to overwrite existing export in {folder}")

        pjs_path.write_text(extracted["main.pjs"], encoding="utf-8")
        html_path.write_text(extracted["index.html"], encoding="utf-8")

        metadata = {
            "url": url,
            "slug": slug,
            "saved_files": ["main.pjs", "index.html", "metadata.json"],
            "extraction": extracted["debug"],
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

        if self.settings.save_debug_json:
            debug_path.write_text(json.dumps(extracted["debug"], indent=2, ensure_ascii=False), encoding="utf-8")
        if self.settings.save_raw_html:
            raw_html_path.write_text(html_text, encoding="utf-8")

        self.log(f"[save] {folder / 'main.pjs'}")
        self.log(f"[save] {folder / 'index.html'}")
        self.log(f"[info] model source: {extracted['debug']['model_source']} | html source: {extracted['debug']['html_source']}")

        return metadata

    def _fetch_with_retries(self, url):
        transient = {408, 425, 429, 500, 502, 503, 504}
        last_error = None
        for attempt in range(1, self.settings.max_retries + 1):
            try:
                self.log(f"[fetch] {url} (attempt {attempt}/{self.settings.max_retries})")
                response = self.session.get(url, timeout=self.settings.timeout_seconds, allow_redirects=True, stream=True)
                if response.status_code in transient:
                    retry_after = response.headers.get("Retry-After")
                    wait_seconds = float(retry_after) if retry_after and retry_after.isdigit() else min(2 ** attempt, 15)
                    raise RetryableHttpError(response.status_code, wait_seconds)
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")
                if "html" not in content_type.lower():
                    raise ValueError(f"Unexpected content type: {content_type}")
                data = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    data.extend(chunk)
                    if len(data) > self.settings.max_response_bytes:
                        raise ValueError("Response exceeded max allowed size")
                return data.decode(response.encoding or "utf-8", errors="replace")
            except RetryableHttpError as exc:
                last_error = exc
                self.log(f"[retry] HTTP {exc.status_code}; waiting {exc.wait_seconds:.2f}s")
                time.sleep(exc.wait_seconds)
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    break
                wait_seconds = min(2 ** attempt, 15)
                self.log(f"[retry] Network error: {exc}; waiting {wait_seconds:.2f}s")
                time.sleep(wait_seconds)
            except Exception as exc:
                last_error = exc
                break
        raise last_error

    @staticmethod
    def _slugify(value):
        value = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
        value = re.sub(r"-+", "-", value).strip("-._")
        return value or "perchance-item"


class RetryableHttpError(Exception):
    def __init__(self, status_code, wait_seconds):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.wait_seconds = wait_seconds


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, settings):
        super().__init__(master)
        self.title("Settings")
        self.resizable(False, False)
        self.settings = settings
        self.result = None

        self.vars = {
            "timeout_seconds": tk.IntVar(value=settings.timeout_seconds),
            "delay_min_seconds": tk.DoubleVar(value=settings.delay_min_seconds),
            "delay_max_seconds": tk.DoubleVar(value=settings.delay_max_seconds),
            "max_retries": tk.IntVar(value=settings.max_retries),
            "allow_off_domain": tk.BooleanVar(value=settings.allow_off_domain),
            "respect_robots_txt": tk.BooleanVar(value=settings.respect_robots_txt),
            "save_raw_html": tk.BooleanVar(value=settings.save_raw_html),
            "save_manifest": tk.BooleanVar(value=settings.save_manifest),
            "save_debug_json": tk.BooleanVar(value=settings.save_debug_json),
            "overwrite_existing": tk.BooleanVar(value=settings.overwrite_existing),
            "max_response_bytes": tk.IntVar(value=settings.max_response_bytes),
        }

        fields = [
            ("Timeout (seconds)", "timeout_seconds"),
            ("Delay min (seconds)", "delay_min_seconds"),
            ("Delay max (seconds)", "delay_max_seconds"),
            ("Max retries", "max_retries"),
            ("Max response bytes", "max_response_bytes"),
        ]
        row = 0
        for label_text, key in fields:
            ttk.Label(self, text=label_text).grid(row=row, column=0, sticky="w", padx=10, pady=6)
            ttk.Entry(self, textvariable=self.vars[key], width=18).grid(row=row, column=1, sticky="ew", padx=10, pady=6)
            row += 1

        checks = [
            ("Allow off-domain scraping", "allow_off_domain"),
            ("Respect robots.txt", "respect_robots_txt"),
            ("Save raw page HTML", "save_raw_html"),
            ("Save manifest.json", "save_manifest"),
            ("Save debug.json", "save_debug_json"),
            ("Overwrite existing files", "overwrite_existing"),
        ]
        for label_text, key in checks:
            ttk.Checkbutton(self, text=label_text, variable=self.vars[key]).grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=4)
            row += 1

        buttons = ttk.Frame(self)
        buttons.grid(row=row, column=0, columnspan=2, sticky="e", padx=10, pady=10)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Save", command=self.on_save).pack(side="right")

        self.transient(master)
        self.grab_set()

    def on_save(self):
        try:
            result = ScraperSettings(
                timeout_seconds=int(self.vars["timeout_seconds"].get()),
                delay_min_seconds=float(self.vars["delay_min_seconds"].get()),
                delay_max_seconds=float(self.vars["delay_max_seconds"].get()),
                max_retries=int(self.vars["max_retries"].get()),
                allow_off_domain=bool(self.vars["allow_off_domain"].get()),
                respect_robots_txt=bool(self.vars["respect_robots_txt"].get()),
                save_raw_html=bool(self.vars["save_raw_html"].get()),
                save_manifest=bool(self.vars["save_manifest"].get()),
                save_debug_json=bool(self.vars["save_debug_json"].get()),
                overwrite_existing=bool(self.vars["overwrite_existing"].get()),
                max_response_bytes=int(self.vars["max_response_bytes"].get()),
            )
            if result.delay_min_seconds < 0 or result.delay_max_seconds < result.delay_min_seconds:
                raise ValueError("Delay range is invalid.")
            self.result = result
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Settings Error", str(exc), parent=self)


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=14)
        self.master = master
        self.settings = ScraperSettings()
        self.log_queue = queue.Queue()
        self.output_dir = tk.StringVar(value=str(Path.cwd() / "perchance_exports"))
        self.status_var = tk.StringVar(value="Idle")
        self.preview_model_var = tk.StringVar(value="No preview yet.")
        self.preview_html_var = tk.StringVar(value="No preview yet.")
        self._build_ui()
        self._poll_logs()

    def _build_ui(self):
        self.master.title(APP_TITLE)
        self.master.geometry("1180x860")
        self.master.minsize(1000, 720)
        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self.rowconfigure(4, weight=1)

        ttk.Label(self, text="Perchance Source Scraper", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            self,
            text="Exports main.pjs from modelText and index.html from outputTemplate. Includes robots checks, throttling, retries, previews, and safer URL validation.",
            wraplength=1100,
        ).grid(row=1, column=0, sticky="w", pady=(6, 12))

        top = ttk.Panedwindow(self, orient="horizontal")
        top.grid(row=2, column=0, sticky="nsew")

        left = ttk.Frame(top, padding=4)
        right = ttk.Frame(top, padding=4)
        top.add(left, weight=3)
        top.add(right, weight=2)

        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        ttk.Label(left, text="URLs (one per line)").grid(row=0, column=0, sticky="w")
        self.url_text = tk.Text(left, height=14, wrap="word", undo=True)
        self.url_text.grid(row=1, column=0, sticky="nsew", pady=(4, 8))

        controls = ttk.Frame(left)
        controls.grid(row=2, column=0, sticky="ew")
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="Output folder").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(controls, textvariable=self.output_dir).grid(row=0, column=1, sticky="ew")
        ttk.Button(controls, text="Browse...", command=self.choose_output_dir).grid(row=0, column=2, padx=(8, 0))

        actions = ttk.Frame(left)
        actions.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        for i in range(6):
            actions.columnconfigure(i, weight=0)
        actions.columnconfigure(6, weight=1)
        self.scrape_button = ttk.Button(actions, text="Scrape URLs", command=self.start_scrape)
        self.scrape_button.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Settings", command=self.open_settings).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text="Load Example URLs", command=self.load_examples).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(actions, text="Import .txt", command=self.import_url_file).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(actions, text="Clear URLs", command=self.clear_urls).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(actions, text="Open Output Folder", command=self.open_output_folder).grid(row=0, column=5)
        ttk.Label(actions, textvariable=self.status_var).grid(row=0, column=7, sticky="e")

        preview_model = ttk.LabelFrame(right, text="main.pjs preview", padding=8)
        preview_model.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        preview_model.columnconfigure(0, weight=1)
        preview_model.rowconfigure(0, weight=1)
        self.preview_model = tk.Text(preview_model, wrap="word", height=12, state="disabled")
        self.preview_model.grid(row=0, column=0, sticky="nsew")

        preview_html = ttk.LabelFrame(right, text="index.html preview", padding=8)
        preview_html.grid(row=1, column=0, sticky="nsew")
        preview_html.columnconfigure(0, weight=1)
        preview_html.rowconfigure(0, weight=1)
        self.preview_html = tk.Text(preview_html, wrap="word", height=12, state="disabled")
        self.preview_html.grid(row=0, column=0, sticky="nsew")

        log_frame = ttk.LabelFrame(self, text="Log", padding=10)
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, wrap="word", state="disabled", background="#111827", foreground="#f9fafb", insertbackground="#f9fafb")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

        footer = ttk.LabelFrame(self, text="Current Settings", padding=8)
        footer.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        footer.columnconfigure(0, weight=1)
        self.settings_label = ttk.Label(footer, text=self._settings_summary(), wraplength=1120)
        self.settings_label.grid(row=0, column=0, sticky="w")

    def _settings_summary(self):
        s = self.settings
        return (
            f"Timeout={s.timeout_seconds}s | Delay={s.delay_min_seconds:.1f}-{s.delay_max_seconds:.1f}s | "
            f"Retries={s.max_retries} | Robots={'on' if s.respect_robots_txt else 'off'} | "
            f"Off-domain={'on' if s.allow_off_domain else 'off'} | Raw HTML={'on' if s.save_raw_html else 'off'}"
        )

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

    def import_url_file(self):
        path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if not path:
            return
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        self.url_text.insert(tk.END, ("\n" if self.url_text.get("1.0", tk.END).strip() else "") + text.strip())

    def clear_urls(self):
        self.url_text.delete("1.0", tk.END)

    def open_output_folder(self):
        path = Path(self.output_dir.get()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        try:
            import os
            os.startfile(path)
        except Exception:
            messagebox.showinfo("Output Folder", str(path))

    def open_settings(self):
        dialog = SettingsDialog(self.master, self.settings)
        self.master.wait_window(dialog)
        if dialog.result:
            self.settings = dialog.result
            self.settings_label.configure(text=self._settings_summary())
            self._log("[settings] Updated scraper settings")

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
        threading.Thread(target=self._run_scrape, args=(urls, out_dir), daemon=True).start()

    def _run_scrape(self, urls, out_dir):
        try:
            scraper = PerchanceScraper(self.settings, self._queue_log)
            summary = scraper.scrape_many(urls, out_dir)
            self.log_queue.put(("done", summary, out_dir))
        except Exception as exc:
            self.log_queue.put(("fatal", str(exc), None))

    def _queue_log(self, message):
        self.log_queue.put(("log", message, None))

    def _poll_logs(self):
        try:
            while True:
                kind, payload, extra = self.log_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "done":
                    self.scrape_button.configure(state="normal")
                    self.status_var.set(f"Complete: {payload['saved']} saved, {payload['failed']} failed, {payload['skipped']} skipped")
                    self._load_last_preview(extra, payload)
                    messagebox.showinfo(APP_TITLE, f"Finished. Saved: {payload['saved']} | Failed: {payload['failed']} | Skipped: {payload['skipped']}")
                elif kind == "fatal":
                    self.scrape_button.configure(state="normal")
                    self.status_var.set("Failed")
                    self._log(f"[fatal] {payload}")
                    messagebox.showerror(APP_TITLE, payload)
        except queue.Empty:
            pass
        self.after(120, self._poll_logs)

    def _load_last_preview(self, out_dir, summary):
        try:
            items = summary.get("items") or []
            if not items:
                return
            last = items[-1]
            folder = Path(out_dir) / last["slug"]
            pjs = (folder / "main.pjs").read_text(encoding="utf-8", errors="replace")[:5000]
            html = (folder / "index.html").read_text(encoding="utf-8", errors="replace")[:5000]
            self._set_preview(self.preview_model, pjs)
            self._set_preview(self.preview_html, html)
        except Exception as exc:
            self._log(f"[preview] Failed to load preview: {exc}")

    def _set_preview(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state="disabled")

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
