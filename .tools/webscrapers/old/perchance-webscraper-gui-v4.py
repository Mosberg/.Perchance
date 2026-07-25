#!/usr/bin/env python3
from __future__ import annotations

import csv
import html
import ipaddress
import json
import queue
import random
import re
import socket
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests
import tkinter as tk
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from tkinter import ttk
from urllib3.util.retry import Retry


APP_TITLE = "Perchance Web Scraper Pro"
USER_AGENT = (
    "PerchanceScraperPro/1.0 (+respectful single-user archival tool; "
    "contact-local-user)"
)

FAVICON_DATA_URI = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
    "%3Crect width='64' height='64' rx='14' fill='%23111827'/%3E"
    "%3Cpath d='M18 14h18c9 0 14 4 14 11 0 5-3 8-8 10 6 2 10 6 10 13 0 10-8 16-19 16H18V14zm11 8v10h6c4 0 7-2 7-5s-3-5-7-5h-6zm0 18v13h8c5 0 8-2 8-6 0-5-3-7-9-7h-7z' fill='white'/%3E"
    "%3C/svg%3E"
)

WRAPPER_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="icon" href="{favicon}">
  <meta name="color-scheme" content="dark light">
  <style>
    :root {{
      color-scheme: dark light;
      --bg: #0f172a;
      --fg: #f8fafc;
      --muted: #94a3b8;
      --panel: rgba(15, 23, 42, 0.82);
      --accent: #22c55e;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; margin: 0; }}
    body {{
      display: grid;
      place-items: center;
      background:
        radial-gradient(circle at top, rgba(34, 197, 94, 0.14), transparent 38%),
        linear-gradient(180deg, #020617 0%, #0f172a 100%);
      color: var(--fg);
      font-family: Inter, "Segoe UI", system-ui, sans-serif;
    }}
    .shell {{
      width: min(94vw, 1080px);
      min-height: min(88vh, 860px);
      display: grid;
      grid-template-rows: auto 1fr;
      overflow: hidden;
      border-radius: 20px;
      border: 1px solid rgba(255,255,255,0.08);
      background: var(--panel);
      box-shadow: 0 20px 70px rgba(0,0,0,.32);
      backdrop-filter: blur(18px);
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 16px 18px;
      border-bottom: 1px solid rgba(255,255,255,0.08);
    }}
    .title {{ font-weight: 700; }}
    .meta {{ color: var(--muted); font-size: 0.92rem; }}
    iframe {{ width: 100%; height: 100%; border: 0; background: white; }}
    .loader {{
      position: fixed; inset: 0; display: grid; place-items: center;
      background: rgba(2,6,23,.72); z-index: 10; transition: opacity .18s ease;
    }}
    .loader[data-hidden="true"] {{ opacity: 0; pointer-events: none; }}
    .spinner {{
      width: 46px; height: 46px; border-radius: 999px;
      border: 3px solid rgba(255,255,255,.16); border-top-color: var(--accent);
      animation: spin .8s linear infinite; margin: 0 auto 12px;
    }}
    .card {{ text-align:center; padding: 24px; }}
    .small {{ color: var(--muted); }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  </style>
</head>
<body>
  <div class="loader" id="loader" aria-live="polite">
    <div class="card">
      <div class="spinner" aria-hidden="true"></div>
      <div><strong>Loading saved wrapper</strong></div>
      <div class="small">This export points to the original public Perchance URL.</div>
    </div>
  </div>
  <div class="shell">
    <header class="header">
      <div class="title">{title}</div>
      <div class="meta">{source_url}</div>
    </header>
    <iframe src="{escaped_url}" title="{title}" loading="eager"></iframe>
  </div>
  <script>
    const loader = document.getElementById("loader");
    window.addEventListener("load", () => loader.setAttribute("data-hidden", "true"), {{ once: true }});
    setTimeout(() => loader.setAttribute("data-hidden", "true"), 2500);
  </script>
</body>
</html>
"""


@dataclass
class ScraperConfig:
    request_timeout: int = 25
    connect_timeout: int = 10
    max_response_bytes: int = 8 * 1024 * 1024
    max_retries: int = 3
    backoff_factor: float = 1.5
    min_delay_seconds: float = 2.0
    max_jitter_seconds: float = 1.25
    max_redirects: int = 5
    respect_robots: bool = True
    dry_run: bool = False
    save_raw_html: bool = True
    save_manifest: bool = True
    save_csv_report: bool = True
    save_wrapper_html: bool = True
    save_pjs: bool = True
    allowed_domains_only: bool = True
    allowed_domains: tuple[str, ...] = ("perchance.org",)
    cooldown_on_429_default: int = 60
    robots_cache_ttl_seconds: int = 3600
    user_agent: str = USER_AGENT
    preset_name: str = "Balanced"


@dataclass
class ScrapeJob:
    url: str
    normalized_url: str
    slug: str
    domain: str


@dataclass
class ScrapeResult:
    url: str
    normalized_url: str
    final_url: str | None = None
    title: str | None = None
    slug: str | None = None
    success: bool = False
    status_code: int | None = None
    error: str | None = None
    robots_allowed: bool | None = None
    extracted_model_script: bool = False
    extracted_model_text: bool = False
    extracted_output_template: bool = False
    folder: str | None = None
    files: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


class DomainRateLimiter:
    def __init__(self, min_delay_seconds: float, max_jitter_seconds: float):
        self.min_delay_seconds = min_delay_seconds
        self.max_jitter_seconds = max_jitter_seconds
        self._next_allowed: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, domain: str, logger, cancel_event: threading.Event):
        with self._lock:
            now = time.time()
            next_allowed = self._next_allowed.get(domain, now)
            wait_for = max(0.0, next_allowed - now)

        if wait_for > 0:
            logger(f"[wait] {domain} sleeping {wait_for:.2f}s for rate limit")
            end = time.time() + wait_for
            while time.time() < end:
                if cancel_event.is_set():
                    return
                time.sleep(0.1)

        jitter = random.uniform(0, self.max_jitter_seconds)
        with self._lock:
            self._next_allowed[domain] = time.time() + self.min_delay_seconds + jitter

    def cooldown(self, domain: str, seconds: float):
        with self._lock:
            self._next_allowed[domain] = max(self._next_allowed.get(domain, 0), time.time() + seconds)


class RobotsCache:
    def __init__(self, ttl_seconds: int, user_agent: str):
        self.ttl_seconds = ttl_seconds
        self.user_agent = user_agent
        self._cache: dict[str, tuple[float, RobotFileParser]] = {}
        self._lock = threading.Lock()

    def _robots_url(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    def can_fetch(self, url: str, session: requests.Session, logger) -> bool:
        robots_url = self._robots_url(url)
        with self._lock:
            cached = self._cache.get(robots_url)
            if cached and (time.time() - cached[0] < self.ttl_seconds):
                parser = cached[1]
                return parser.can_fetch(self.user_agent, url)

        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            logger(f"[robots] fetching {robots_url}")
            res = session.get(robots_url, timeout=(8, 15), allow_redirects=True)
            if res.ok:
                parser.parse(res.text.splitlines())
            else:
                parser.parse([])
        except Exception:
            parser.parse([])

        with self._lock:
            self._cache[robots_url] = (time.time(), parser)

        return parser.can_fetch(self.user_agent, url)


class SafeFetcher:
    RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}

    def __init__(self, config: ScraperConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
            "Referer": "https://perchance.org/",
        })
        retry = Retry(
            total=0,
            connect=0,
            read=0,
            status=0,
            redirect=config.max_redirects,
            backoff_factor=0,
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def fetch_html(self, url: str, domain_limiter: DomainRateLimiter, logger, cancel_event: threading.Event):
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        last_error = None
        for attempt in range(1, self.config.max_retries + 2):
            if cancel_event.is_set():
                raise RuntimeError("Cancelled")

            domain_limiter.wait(domain, logger, cancel_event)
            if cancel_event.is_set():
                raise RuntimeError("Cancelled")

            try:
                logger(f"[fetch] attempt {attempt}: {url}")
                res = self.session.get(
                    url,
                    timeout=(self.config.connect_timeout, self.config.request_timeout),
                    allow_redirects=True,
                    stream=True,
                )
                status = res.status_code

                if status in self.RETRY_STATUSES:
                    retry_after = self._parse_retry_after(res.headers.get("Retry-After"))
                    if status == 429:
                        cooldown = retry_after if retry_after is not None else self.config.cooldown_on_429_default
                        logger(f"[rate-limit] 429 for {url}; cooldown {cooldown}s")
                        domain_limiter.cooldown(domain, cooldown)

                    if attempt <= self.config.max_retries:
                        delay = retry_after if retry_after is not None else self._backoff(attempt)
                        logger(f"[retry] status {status}; sleeping {delay:.2f}s")
                        self._interruptible_sleep(delay, cancel_event)
                        continue

                if status == 403:
                    raise PermissionError("403 Forbidden; not retrying")
                if status == 404:
                    raise FileNotFoundError("404 Not Found; not retrying")

                res.raise_for_status()

                content_type = (res.headers.get("Content-Type") or "").lower()
                if "html" not in content_type and "text/plain" not in content_type:
                    raise ValueError(f"Unexpected content type: {content_type}")

                body = self._read_limited_body(res)
                return res, body

            except Exception as exc:
                last_error = exc
                transient = isinstance(exc, (requests.Timeout, requests.ConnectionError))
                if transient and attempt <= self.config.max_retries:
                    delay = self._backoff(attempt)
                    logger(f"[retry] transient error: {exc}; sleeping {delay:.2f}s")
                    self._interruptible_sleep(delay, cancel_event)
                    continue
                break

        raise last_error or RuntimeError("Unknown fetch failure")

    def _read_limited_body(self, response: requests.Response) -> str:
        size = 0
        chunks: list[bytes] = []
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue
            size += len(chunk)
            if size > self.config.max_response_bytes:
                raise ValueError(f"Response too large (> {self.config.max_response_bytes} bytes)")
            chunks.append(chunk)
        return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")

    def _backoff(self, attempt: int) -> float:
        base = self.config.backoff_factor * (2 ** (attempt - 1))
        jitter = random.uniform(0, 0.75)
        return min(base + jitter, 120.0)

    @staticmethod
    def _parse_retry_after(value: str | None) -> int | None:
        if not value:
            return None
        value = value.strip()
        if value.isdigit():
            return int(value)
        return None

    @staticmethod
    def _interruptible_sleep(seconds: float, cancel_event: threading.Event):
        end = time.time() + seconds
        while time.time() < end:
            if cancel_event.is_set():
                raise RuntimeError("Cancelled")
            time.sleep(0.1)


class PerchanceExtractor:
    def extract(self, html_text: str) -> dict:
        soup = BeautifulSoup(html_text, "html.parser")

        title = self._extract_title(soup)
        model_script = self._extract_script_by_id(soup, html_text, "modelScript")
        model_text = self._extract_window_assignment(html_text, "modelText")
        output_template = self._extract_window_assignment(html_text, "outputTemplate")
        imported_generators = self._extract_imported_generators(soup, html_text)

        return {
            "title": title,
            "model_script": model_script,
            "model_text": model_text,
            "output_template": output_template,
            "imported_generators": imported_generators,
        }

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        node = soup.find("title")
        if node:
            return node.get_text(" ", strip=True)
        return "Perchance Export"

    @staticmethod
    def _extract_script_by_id(soup: BeautifulSoup, html_text: str, script_id: str) -> str | None:
        node = soup.find("script", id=script_id)
        if node:
            text = node.string if node.string is not None else node.get_text("", strip=False)
            text = (text or "").strip()
            return text + "\n" if text else None

        match = re.search(
            rf'<script[^>]*id=["\']{re.escape(script_id)}["\'][^>]*>(.*?)</script>',
            html_text,
            re.IGNORECASE | re.DOTALL,
        )
        if match:
            text = html.unescape(match.group(1)).strip()
            return text + "\n" if text else None
        return None

    @staticmethod
    def _extract_window_assignment(html_text: str, key: str) -> str | None:
        patterns = [
            rf'window\.{re.escape(key)}\s*=\s*(`(?:\\.|[^`])*`)',
            rf'window\.{re.escape(key)}\s*=\s*("(?:(?:\\.)|[^"])*")',
            rf'window\.{re.escape(key)}\s*=\s*(\'(?:(?:\\.)|[^\'])*\')',
        ]
        for pattern in patterns:
            m = re.search(pattern, html_text, re.DOTALL)
            if m:
                raw = m.group(1)
                try:
                    if raw.startswith("`") and raw.endswith("`"):
                        return raw[1:-1]
                    return json.loads(raw)
                except Exception:
                    return raw[1:-1]
        return None

    @staticmethod
    def _extract_imported_generators(soup: BeautifulSoup, html_text: str):
        node = soup.find(id="imported-generators")
        if node:
            raw = node.get_text("", strip=True)
            if raw:
                try:
                    return json.loads(raw)
                except Exception:
                    return raw

        m = re.search(r'generatorDependenciesData\s*=\s*JSON\.parse\(\s*decodeURI\((.*?)\)\s*\)', html_text, re.DOTALL)
        if m:
            return {"hint": "Embedded dependency payload detected"}
        return None


class PerchanceExporter:
    def __init__(self, output_root: Path, config: ScraperConfig):
        self.output_root = output_root
        self.config = config
        self.output_root.mkdir(parents=True, exist_ok=True)

    def write_result(self, job: ScrapeJob, extracted: dict, html_text: str, final_url: str) -> tuple[str, list[str]]:
        folder = self.output_root / job.slug
        folder.mkdir(parents=True, exist_ok=True)
        files: list[str] = []

        title = extracted.get("title") or job.slug.replace("-", " ").title()

        if self.config.save_pjs and extracted.get("model_script"):
            path = folder / "main.pjs"
            path.write_text(extracted["model_script"], encoding="utf-8")
            files.append(path.name)

        if extracted.get("model_text"):
            path = folder / "modelText.txt"
            path.write_text(extracted["model_text"], encoding="utf-8")
            files.append(path.name)

        if extracted.get("output_template"):
            path = folder / "outputTemplate.html"
            path.write_text(extracted["output_template"], encoding="utf-8")
            files.append(path.name)

        if extracted.get("imported_generators") is not None:
            path = folder / "imports.json"
            path.write_text(json.dumps(extracted["imported_generators"], indent=2, ensure_ascii=False), encoding="utf-8")
            files.append(path.name)

        if self.config.save_wrapper_html:
            path = folder / "index.html"
            path.write_text(self._build_wrapper(title, final_url), encoding="utf-8")
            files.append(path.name)

        if self.config.save_raw_html:
            path = folder / "source.html"
            path.write_text(html_text, encoding="utf-8")
            files.append(path.name)

        meta = {
            "title": title,
            "slug": job.slug,
            "requested_url": job.url,
            "normalized_url": job.normalized_url,
            "final_url": final_url,
            "saved_files": files,
            "timestamp_unix": int(time.time()),
        }
        meta_path = folder / "metadata.json"
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        files.append(meta_path.name)

        return str(folder), files

    @staticmethod
    def _build_wrapper(title: str, source_url: str) -> str:
        return WRAPPER_TEMPLATE.format(
            title=html.escape(title),
            favicon=FAVICON_DATA_URI,
            source_url=html.escape(source_url),
            escaped_url=html.escape(source_url, quote=True),
        )


class PerchanceScraperEngine:
    def __init__(self, config: ScraperConfig, output_dir: Path, logger):
        self.config = config
        self.output_dir = Path(output_dir)
        self.logger = logger
        self.fetcher = SafeFetcher(config)
        self.extractor = PerchanceExtractor()
        self.exporter = PerchanceExporter(self.output_dir, config)
        self.robots = RobotsCache(config.robots_cache_ttl_seconds, config.user_agent)
        self.limiter = DomainRateLimiter(config.min_delay_seconds, config.max_jitter_seconds)

    def run(self, urls: list[str], cancel_event: threading.Event) -> list[ScrapeResult]:
        jobs = self._prepare_jobs(urls)
        self.logger(f"[queue] {len(jobs)} unique URL(s) ready")
        results: list[ScrapeResult] = []

        for idx, job in enumerate(jobs, start=1):
            if cancel_event.is_set():
                self.logger("[cancel] stopping queue")
                break

            self.logger(f"[job] {idx}/{len(jobs)} {job.normalized_url}")
            started = time.time()
            result = ScrapeResult(
                url=job.url,
                normalized_url=job.normalized_url,
                slug=job.slug,
            )

            try:
                if self.config.respect_robots:
                    allowed = self.robots.can_fetch(job.normalized_url, self.fetcher.session, self.logger)
                    result.robots_allowed = allowed
                    if not allowed:
                        raise PermissionError("Blocked by robots.txt")

                if self.config.dry_run:
                    result.success = True
                    result.elapsed_seconds = time.time() - started
                    results.append(result)
                    continue

                response, html_text = self.fetcher.fetch_html(job.normalized_url, self.limiter, self.logger, cancel_event)
                result.final_url = response.url
                result.status_code = response.status_code

                extracted = self.extractor.extract(html_text)
                result.title = extracted.get("title")
                result.extracted_model_script = bool(extracted.get("model_script"))
                result.extracted_model_text = bool(extracted.get("model_text"))
                result.extracted_output_template = bool(extracted.get("output_template"))

                if not extracted.get("model_script") and not extracted.get("model_text"):
                    raise ValueError("No Perchance source payload found")

                folder, files = self.exporter.write_result(job, extracted, html_text, response.url)
                result.folder = folder
                result.files = files
                result.success = True

            except Exception as exc:
                result.error = str(exc)
                self.logger(f"[error] {job.normalized_url} -> {exc}")

            result.elapsed_seconds = time.time() - started
            results.append(result)

        if self.config.save_manifest:
            self._save_manifest(results)

        if self.config.save_csv_report:
            self._save_csv(results)

        return results

    def _save_manifest(self, results: list[ScrapeResult]):
        path = self.output_dir / "run-manifest.json"
        payload = {
            "config": asdict(self.config),
            "results": [asdict(r) for r in results],
            "generated_at_unix": int(time.time()),
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _save_csv(self, results: list[ScrapeResult]):
        path = self.output_dir / "run-report.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "url", "normalized_url", "final_url", "title", "slug", "success",
                "status_code", "robots_allowed", "extracted_model_script",
                "extracted_model_text", "extracted_output_template",
                "folder", "error", "elapsed_seconds",
            ])
            writer.writeheader()
            for r in results:
                writer.writerow({
                    "url": r.url,
                    "normalized_url": r.normalized_url,
                    "final_url": r.final_url,
                    "title": r.title,
                    "slug": r.slug,
                    "success": r.success,
                    "status_code": r.status_code,
                    "robots_allowed": r.robots_allowed,
                    "extracted_model_script": r.extracted_model_script,
                    "extracted_model_text": r.extracted_model_text,
                    "extracted_output_template": r.extracted_output_template,
                    "folder": r.folder,
                    "error": r.error,
                    "elapsed_seconds": f"{r.elapsed_seconds:.3f}",
                })

    def _prepare_jobs(self, urls: list[str]) -> list[ScrapeJob]:
        seen = set()
        jobs = []

        for raw in urls:
            normalized = normalize_url(raw)
            if not normalized:
                self.logger(f"[skip] invalid URL: {raw}")
                continue

            if not is_safe_public_url(normalized):
                self.logger(f"[skip] unsafe/private URL blocked: {normalized}")
                continue

            parsed = urlparse(normalized)
            domain = parsed.netloc.lower()

            if self.config.allowed_domains_only and not domain_allowed(domain, self.config.allowed_domains):
                self.logger(f"[skip] domain not allowed: {domain}")
                continue

            key = normalized.lower()
            if key in seen:
                self.logger(f"[skip] duplicate: {normalized}")
                continue
            seen.add(key)

            slug = slugify(parsed.path.strip("/") or domain.split(".")[0] or "perchance-item")
            jobs.append(ScrapeJob(
                url=raw.strip(),
                normalized_url=normalized,
                slug=slug,
                domain=domain,
            ))

        return jobs


def normalize_url(raw: str) -> str | None:
    if not raw or not raw.strip():
        return None
    value = raw.strip()
    if not re.match(r"^https?://", value, re.IGNORECASE):
        value = "https://" + value.lstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    parsed = parsed._replace(
        fragment="",
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
    )

    path = parsed.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    parsed = parsed._replace(path=path)

    return urlunparse(parsed)


def domain_allowed(domain: str, allowed_domains: tuple[str, ...]) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in allowed_domains)


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
    value = re.sub(r"-+", "-", value).strip("-._")
    return value or "perchance-item"


def is_safe_public_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False

    forbidden_hosts = {"localhost"}
    if host.lower() in forbidden_hosts:
        return False

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local or
            ip.is_reserved or ip.is_multicast
        ):
            return False
    return True


class ScraperApp(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=14)
        self.master = master
        self.log_queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker_thread = None

        self.output_dir = tk.StringVar(value=str(Path.cwd() / "perchance_exports"))
        self.preset_var = tk.StringVar(value="Balanced")
        self.status_var = tk.StringVar(value="Idle")
        self.progress_var = tk.DoubleVar(value=0.0)

        self.min_delay_var = tk.StringVar(value="2.0")
        self.max_jitter_var = tk.StringVar(value="1.25")
        self.max_retries_var = tk.StringVar(value="3")
        self.timeout_var = tk.StringVar(value="25")
        self.allowed_domains_only_var = tk.BooleanVar(value=True)
        self.respect_robots_var = tk.BooleanVar(value=True)
        self.dry_run_var = tk.BooleanVar(value=False)
        self.save_raw_html_var = tk.BooleanVar(value=True)
        self.save_manifest_var = tk.BooleanVar(value=True)
        self.save_csv_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._poll_logs()

    def _build_ui(self):
        self.master.title(APP_TITLE)
        self.master.geometry("1100x860")
        self.master.minsize(980, 720)

        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text=APP_TITLE, font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Respectful multi-URL Perchance scraper with robots checks, rate limits, retries, and structured exports.",
            wraplength=1000,
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))

        input_box = ttk.LabelFrame(self, text="URLs", padding=12)
        input_box.grid(row=1, column=0, sticky="nsew")
        input_box.columnconfigure(0, weight=1)
        input_box.rowconfigure(0, weight=1)

        self.url_text = tk.Text(input_box, height=12, wrap="word", undo=True)
        self.url_text.grid(row=0, column=0, sticky="nsew")

        settings = ttk.LabelFrame(self, text="Settings", padding=12)
        settings.grid(row=2, column=0, sticky="ew", pady=10)
        for i in range(8):
            settings.columnconfigure(i, weight=1)

        ttk.Label(settings, text="Preset").grid(row=0, column=0, sticky="w")
        preset_combo = ttk.Combobox(settings, textvariable=self.preset_var, values=["Gentle", "Balanced", "Fast"], state="readonly")
        preset_combo.grid(row=0, column=1, sticky="ew", padx=(6, 10))
        preset_combo.bind("<<ComboboxSelected>>", self.apply_preset)

        ttk.Label(settings, text="Min delay (s)").grid(row=0, column=2, sticky="w")
        ttk.Entry(settings, textvariable=self.min_delay_var, width=10).grid(row=0, column=3, sticky="ew", padx=(6, 10))

        ttk.Label(settings, text="Jitter max (s)").grid(row=0, column=4, sticky="w")
        ttk.Entry(settings, textvariable=self.max_jitter_var, width=10).grid(row=0, column=5, sticky="ew", padx=(6, 10))

        ttk.Label(settings, text="Max retries").grid(row=0, column=6, sticky="w")
        ttk.Entry(settings, textvariable=self.max_retries_var, width=10).grid(row=0, column=7, sticky="ew", padx=(6, 0))

        ttk.Label(settings, text="Timeout (s)").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(settings, textvariable=self.timeout_var, width=10).grid(row=1, column=1, sticky="ew", padx=(6, 10), pady=(10, 0))

        ttk.Checkbutton(settings, text="Respect robots.txt", variable=self.respect_robots_var).grid(row=1, column=2, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Checkbutton(settings, text="Perchance domains only", variable=self.allowed_domains_only_var).grid(row=1, column=4, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Checkbutton(settings, text="Dry run only", variable=self.dry_run_var).grid(row=1, column=6, columnspan=2, sticky="w", pady=(10, 0))

        ttk.Checkbutton(settings, text="Save raw HTML", variable=self.save_raw_html_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Checkbutton(settings, text="Save manifest JSON", variable=self.save_manifest_var).grid(row=2, column=2, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Checkbutton(settings, text="Save CSV report", variable=self.save_csv_var).grid(row=2, column=4, columnspan=2, sticky="w", pady=(10, 0))

        output_box = ttk.LabelFrame(self, text="Output", padding=12)
        output_box.grid(row=3, column=0, sticky="ew")
        output_box.columnconfigure(1, weight=1)

        ttk.Label(output_box, text="Folder").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(output_box, textvariable=self.output_dir).grid(row=0, column=1, sticky="ew")
        ttk.Button(output_box, text="Browse...", command=self.choose_output_dir).grid(row=0, column=2, padx=(8, 0))

        actions = ttk.Frame(output_box)
        actions.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        actions.columnconfigure(10, weight=1)

        self.start_btn = ttk.Button(actions, text="Start Scrape", command=self.start_scrape)
        self.start_btn.grid(row=0, column=0, padx=(0, 8))
        self.cancel_btn = ttk.Button(actions, text="Cancel", command=self.cancel_scrape, state="disabled")
        self.cancel_btn.grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text="Load Example URLs", command=self.load_examples).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(actions, text="Import .txt", command=self.import_txt).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(actions, text="Clear URLs", command=self.clear_urls).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(actions, text="Open Output Folder", command=self.open_output_folder).grid(row=0, column=5)

        ttk.Label(actions, textvariable=self.status_var).grid(row=0, column=11, sticky="e")

        progress = ttk.Progressbar(output_box, variable=self.progress_var, maximum=100)
        progress.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        log_box = ttk.LabelFrame(self, text="Log", padding=12)
        log_box.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        log_box.columnconfigure(0, weight=1)
        log_box.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_box,
            height=18,
            wrap="word",
            state="disabled",
            background="#111827",
            foreground="#f9fafb",
            insertbackground="#f9fafb",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(log_box, orient="vertical", command=self.log_text.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=yscroll.set)

    def apply_preset(self, *_):
        preset = self.preset_var.get()
        if preset == "Gentle":
            self.min_delay_var.set("3.0")
            self.max_jitter_var.set("1.8")
            self.max_retries_var.set("2")
            self.timeout_var.set("30")
        elif preset == "Balanced":
            self.min_delay_var.set("2.0")
            self.max_jitter_var.set("1.25")
            self.max_retries_var.set("3")
            self.timeout_var.set("25")
        elif preset == "Fast":
            self.min_delay_var.set("1.0")
            self.max_jitter_var.set("0.5")
            self.max_retries_var.set("2")
            self.timeout_var.set("20")

    def choose_output_dir(self):
        path = filedialog.askdirectory(initialdir=self.output_dir.get() or str(Path.cwd()))
        if path:
            self.output_dir.set(path)

    def import_txt(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        existing = self.url_text.get("1.0", tk.END).strip()
        if existing:
            self.url_text.insert(tk.END, "\n" + content.strip() + "\n")
        else:
            self.url_text.insert("1.0", content.strip() + "\n")

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
            messagebox.showinfo(APP_TITLE, f"Output folder:\n{path}")

    def start_scrape(self):
        urls = [line.strip() for line in self.url_text.get("1.0", tk.END).splitlines() if line.strip()]
        if not urls:
            messagebox.showwarning(APP_TITLE, "Paste at least one URL.")
            return

        try:
            config = ScraperConfig(
                request_timeout=int(self.timeout_var.get().strip()),
                max_retries=int(self.max_retries_var.get().strip()),
                min_delay_seconds=float(self.min_delay_var.get().strip()),
                max_jitter_seconds=float(self.max_jitter_var.get().strip()),
                respect_robots=self.respect_robots_var.get(),
                dry_run=self.dry_run_var.get(),
                save_raw_html=self.save_raw_html_var.get(),
                save_manifest=self.save_manifest_var.get(),
                save_csv_report=self.save_csv_var.get(),
                allowed_domains_only=self.allowed_domains_only_var.get(),
                preset_name=self.preset_var.get(),
            )
        except ValueError:
            messagebox.showerror(APP_TITLE, "One or more settings are invalid.")
            return

        out_dir = Path(self.output_dir.get().strip()).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)

        self.cancel_event.clear()
        self.progress_var.set(0)
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.status_var.set("Running...")
        self._log(f"[start] {len(urls)} input URL(s)")

        self.worker_thread = threading.Thread(
            target=self._run_worker,
            args=(urls, out_dir, config),
            daemon=True,
        )
        self.worker_thread.start()

    def cancel_scrape(self):
        self.cancel_event.set()
        self._log("[cancel] cancellation requested")
        self.status_var.set("Cancelling...")

    def _run_worker(self, urls, out_dir: Path, config: ScraperConfig):
        try:
            engine = PerchanceScraperEngine(config, out_dir, self._queue_log)
            results = engine.run(urls, self.cancel_event)

            total = len(results)
            ok = sum(1 for r in results if r.success)
            fail = total - ok
            self.log_queue.put(("done", {"total": total, "ok": ok, "fail": fail}))
        except Exception as exc:
            self.log_queue.put(("fatal", str(exc)))

    def _queue_log(self, msg: str):
        self.log_queue.put(("log", msg))

    def _poll_logs(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "done":
                    self.start_btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
                    self.progress_var.set(100)
                    self.status_var.set(f"Done: {payload['ok']} ok, {payload['fail']} failed")
                    messagebox.showinfo(APP_TITLE, f"Completed.\nSuccess: {payload['ok']}\nFailed: {payload['fail']}")
                elif kind == "fatal":
                    self.start_btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
                    self.status_var.set("Failed")
                    self._log(f"[fatal] {payload}")
                    messagebox.showerror(APP_TITLE, payload)
        except queue.Empty:
            pass

        self.after(120, self._poll_logs)

    def _log(self, message: str):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")


def main():
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("clam")
    except tk.TclError:
        pass
    app = ScraperApp(root)
    app.apply_preset()
    app.mainloop()


if __name__ == "__main__":
    main()