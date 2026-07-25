import os
import re
import requests
from urllib.parse import urlparse

FAVICON_URL = "https://user.uploads.dev/file/8c7563d0ece7c9ed36c8a83f8361a7a7.webp"

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>{title}</title>
<link rel="shortcut icon" href="{favicon}" type="image/x-icon" />
</head>
<body>
<script src="{pjs_file}"></script>
</body>
</html>
"""

def sanitize_filename(name):
    return re.sub(r'[^a-zA-Z0-9-_]+', '-', name).strip('-')

def fetch_perchance_source(url):
    """Fetches the raw Perchance source from a generator/plugin URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        text = response.text

        # Perchance stores code inside <script id="modelScript"> ... </script>
        match = re.search(r'<script[^>]*id="modelScript"[^>]*>(.*?)</script>', text, re.S)
        if not match:
            print(f"[WARN] No modelScript found in {url}")
            return None

        return match.group(1).strip()

    except Exception as e:
        print(f"[ERROR] Failed to fetch {url}: {e}")
        return None

def create_files_from_url(url, output_dir="scraped"):
    """Scrapes a Perchance URL and outputs .pjs + .html files."""
    print(f"[SCRAPE] {url}")

    source = fetch_perchance_source(url)
    if not source:
        return

    parsed = urlparse(url)
    base_name = sanitize_filename(os.path.basename(parsed.path) or "generator")

    pjs_filename = f"{base_name}.pjs"
    html_filename = f"{base_name}.html"

    os.makedirs(output_dir, exist_ok=True)

    # Write .pjs file
    with open(os.path.join(output_dir, pjs_filename), "w", encoding="utf-8") as f:
        f.write(source)

    # Write .html wrapper
    html_content = HTML_TEMPLATE.format(
        title=base_name,
        favicon=FAVICON_URL,
        pjs_file=pjs_filename
    )

    with open(os.path.join(output_dir, html_filename), "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[OK] Created {pjs_filename} + {html_filename}")

def scrape_url_list(url_list, output_dir="scraped"):
    """Scrapes multiple Perchance URLs."""
    for url in url_list:
        url = url.strip()
        if not url:
            continue
        create_files_from_url(url, output_dir)

# Example usage:
if __name__ == "__main__":
    urls = [
        "https://perchance.org/minimal#edit",
        "https://perchance.org/text-to-image-plugin#edit"
    ]
    scrape_url_list(urls)
