import os
import re
import requests
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

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
    """Fetch raw Perchance code from a generator/plugin URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        text = response.text

        match = re.search(
            r'<script[^>]*id="modelScript"[^>]*>(.*?)</script>',
            text,
            re.S
        )
        if not match:
            return None

        return match.group(1).strip()

    except Exception:
        return None

def create_files_from_url(url, output_dir, log_callback):
    """Scrapes a Perchance URL and outputs .pjs + .html files."""
    log_callback(f"[SCRAPE] {url}")

    source = fetch_perchance_source(url)
    if not source:
        log_callback(f"[WARN] No modelScript found in {url}")
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

    log_callback(f"[OK] Created {pjs_filename} + {html_filename}")

def scrape_url_list(url_list, output_dir, log_callback):
    for url in url_list:
        url = url.strip()
        if url:
            create_files_from_url(url, output_dir, log_callback)

# -----------------------------
# Tkinter GUI
# -----------------------------
class PerchanceScraperGUI:
    def __init__(self, root):
        self.root = root
        root.title("Perchance Webscraper")
        root.geometry("800x600")

        # URL input
        ttk.Label(root, text="Enter Perchance URLs (one per line):").pack(anchor="w", padx=10, pady=5)
        self.url_text = tk.Text(root, height=10)
        self.url_text.pack(fill="x", padx=10)

        # Output folder selector
        folder_frame = ttk.Frame(root)
        folder_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(folder_frame, text="Output Folder:").pack(side="left")
        self.output_var = tk.StringVar(value=os.path.abspath("scraped"))
        self.output_entry = ttk.Entry(folder_frame, textvariable=self.output_var, width=50)
        self.output_entry.pack(side="left", padx=5)

        ttk.Button(folder_frame, text="Browse", command=self.choose_folder).pack(side="left")

        # Scrape button
        ttk.Button(root, text="Scrape URLs", command=self.start_scrape).pack(pady=10)

        # Log output
        ttk.Label(root, text="Log Output:").pack(anchor="w", padx=10)
        self.log_text = tk.Text(root, height=20, state="disabled", bg="#111", fg="#0f0")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=5)

    def choose_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_var.set(folder)

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def start_scrape(self):
        urls = self.url_text.get("1.0", "end").strip().split("\n")
        output_dir = self.output_var.get()

        if not urls:
            messagebox.showerror("Error", "Please enter at least one URL.")
            return

        self.log("[START] Scraping...")
        scrape_url_list(urls, output_dir, self.log)
        self.log("[DONE] All URLs processed.")

# Run GUI
if __name__ == "__main__":
    root = tk.Tk()
    app = PerchanceScraperGUI(root)
    root.mainloop()
