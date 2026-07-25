import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


class PerchanceSourceExtractor:
    def __init__(self, timeout=30):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            )
        })
        self.timeout = timeout

    def fetch_html(self, url: str) -> str:
        res = self.session.get(url, timeout=self.timeout)
        res.raise_for_status()
        return res.text

    def extract(self, page_html: str) -> dict:
        soup = BeautifulSoup(page_html, "html.parser")

        model_script = self._extract_model_script(soup, page_html)
        output_template = self._extract_output_template(soup, page_html)
        model_text = self._extract_model_text(soup, page_html)

        if not model_text and model_script:
            model_text = model_script

        return {
            "main.pjs": model_text,
            "index.html": output_template,
        }

    def _extract_model_script(self, soup, raw_html):
        node = soup.find("script", id="modelScript")
        if node:
            if node.string is not None:
                return node.string.strip() + "\n"
            if node.contents:
                return "".join(str(x) for x in node.contents).strip() + "\n"

        m = re.search(
            r'<script[^>]*id=["\']modelScript["\'][^>]*>(.*?)</script>',
            raw_html,
            re.I | re.S,
        )
        if m:
            return html.unescape(m.group(1)).strip() + "\n"
        return None

    def _extract_output_template(self, soup, raw_html):
        candidates = []

        for tag in soup.find_all("template"):
            text = tag.get_text("", strip=False)
            if text and self._looks_like_html_source(text):
                candidates.append(text)

        for tag in soup.find_all("textarea"):
            text = tag.get_text("", strip=False)
            if text and self._looks_like_html_source(text):
                candidates.append(text)

        for tag in soup.find_all("input"):
            value = tag.get("value")
            if value and self._looks_like_html_source(value):
                candidates.append(value)

        script_blocks = soup.find_all("script")
        for script in script_blocks:
            script_text = script.string if script.string is not None else script.get_text("", strip=False)
            if not script_text:
                continue

            for key in ("outputTemplate", "outputTemplateInitialContent"):
                found = self._extract_js_string_assignment(script_text, key)
                if found and self._looks_like_html_source(found):
                    candidates.append(found)

        raw_patterns = [
            r'outputTemplateInitialContent\s*=\s*([\'"`])(?P<val>.*?)(?<!\\)\1',
            r'outputTemplate\s*:\s*([\'"`])(?P<val>.*?)(?<!\\)\1',
            r'"outputTemplate"\s*:\s*"(?P<val>(?:\\.|[^"])*)"',
        ]
        for pattern in raw_patterns:
            for m in re.finditer(pattern, raw_html, re.I | re.S):
                val = m.group("val")
                val = bytes(val, "utf-8").decode("unicode_escape")
                if self._looks_like_html_source(val):
                    candidates.append(val)

        return self._best_candidate(candidates)

    def _extract_model_text(self, soup, raw_html):
        candidates = []

        for tag in soup.find_all("textarea"):
            text = tag.get_text("", strip=False)
            if text and self._looks_like_pjs_source(text):
                candidates.append(text)

        for tag in soup.find_all("input"):
            value = tag.get("value")
            if value and self._looks_like_pjs_source(value):
                candidates.append(value)

        for script in soup.find_all("script"):
            script_text = script.string if script.string is not None else script.get_text("", strip=False)
            if not script_text:
                continue

            for key in ("modelText", "modelTextInitialContent"):
                found = self._extract_js_string_assignment(script_text, key)
                if found and self._looks_like_pjs_source(found):
                    candidates.append(found)

        raw_patterns = [
            r'modelTextInitialContent\s*=\s*([\'"`])(?P<val>.*?)(?<!\\)\1',
            r'modelText\s*:\s*([\'"`])(?P<val>.*?)(?<!\\)\1',
            r'"modelText"\s*:\s*"(?P<val>(?:\\.|[^"])*)"',
        ]
        for pattern in raw_patterns:
            for m in re.finditer(pattern, raw_html, re.I | re.S):
                val = m.group("val")
                val = bytes(val, "utf-8").decode("unicode_escape")
                if self._looks_like_pjs_source(val):
                    candidates.append(val)

        return self._best_candidate(candidates)

    def _extract_js_string_assignment(self, script_text: str, key: str):
        patterns = [
            rf'{re.escape(key)}\s*[:=]\s*([\'"`])(?P<val>.*?)(?<!\\)\1',
            rf'"{re.escape(key)}"\s*:\s*"(?P<val>(?:\\.|[^"])*)"',
        ]
        for pattern in patterns:
            m = re.search(pattern, script_text, re.I | re.S)
            if m:
                val = m.group("val")
                try:
                    return bytes(val, "utf-8").decode("unicode_escape")
                except Exception:
                    return val
        return None

    def _looks_like_html_source(self, text: str) -> bool:
        sample = text.strip().lower()
        if len(sample) < 20:
            return False
        html_signals = ("<div", "<span", "<p", "<style", "<script", "<!doctype", "<html", "</")
        return any(sig in sample for sig in html_signals)

    def _looks_like_pjs_source(self, text: str) -> bool:
        sample = text.strip()
        if len(sample) < 10:
            return False
        return ("\n" in sample and "[" in sample) or ("=" in sample and "\n" in sample) or ("{" in sample and "}" in sample)

    def _best_candidate(self, candidates):
        candidates = [c.strip() + "\n" for c in candidates if c and c.strip()]
        if not candidates:
            return None
        candidates.sort(key=len, reverse=True)
        return candidates[0]

    def export_url(self, url: str, output_root: str | Path):
        output_root = Path(output_root)
        output_root.mkdir(parents=True, exist_ok=True)

        html_text = self.fetch_html(url)
        extracted = self.extract(html_text)

        slug = self._slug_from_url(url)
        folder = output_root / slug
        folder.mkdir(parents=True, exist_ok=True)

        if extracted["main.pjs"]:
            (folder / "main.pjs").write_text(extracted["main.pjs"], encoding="utf-8")
        if extracted["index.html"]:
            (folder / "index.html").write_text(extracted["index.html"], encoding="utf-8")

        metadata = {
            "url": url,
            "slug": slug,
            "has_main_pjs": bool(extracted["main.pjs"]),
            "has_index_html": bool(extracted["index.html"]),
        }
        (folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata

    def _slug_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        slug = parsed.path.strip("/").split("/")[0] or "perchance-item"
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug.lower()).strip("-._")
        return slug or "perchance-item"