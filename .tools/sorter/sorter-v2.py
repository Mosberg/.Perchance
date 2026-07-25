import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# ---------------------------------------------------------
# CATEGORY RULES (expanded)
# ---------------------------------------------------------
CATEGORY_RULES = {
    "Generators": [
        "generator",
        "character",
        "profile",
        "metadata",
        "creator",
        "forge",
        "output",
        "visual",
        "description",
        "sheet",
        "codex",
    ],
    "Plugins": [
        "plugin",
        "framework",
        "kit",
        "tool",
        "router",
        "flags",
        "dashboard",
        "studio",
        "panel",
    ],
    "Styles": ["style", "css", "theme"],
    "Tools": [
        "json",
        "validator",
        "viewer",
        "toolkit",
        "converter",
        "calculator",
        "notepad",
        "browser",
        "winrar",
    ],
    "Games": [
        "game",
        "dnd",
        "pokemon",
        "ant",
        "colony",
        "minecraft",
        "trial",
        "manager",
    ],
    "NSFW": ["nsfw", "adult", "hentai", "porno", "lust", "fuck"],
    "AI": ["ai-", "ai_", "ai "],
    "Misc": [],
}


# ---------------------------------------------------------
# Helper: read .pjs content for metadata-based hints
# ---------------------------------------------------------
def read_pjs_metadata(folder_path: str) -> str:
    """
    Try to read the first .pjs file in the folder and return its content
    (or a snippet). Used for metadata-based classification.
    """
    try:
        for fname in os.listdir(folder_path):
            if fname.endswith(".pjs"):
                pjs_path = os.path.join(folder_path, fname)
                with open(pjs_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(4096)  # read first 4KB
                    return content
    except Exception:
        pass
    return ""


# ---------------------------------------------------------
# Automatic category detection from name + content
# ---------------------------------------------------------
def classify_generator(folder_name: str, folder_path: str) -> str:
    name_lower = folder_name.lower()
    content = read_pjs_metadata(folder_path).lower()

    # 1) NSFW gets priority
    for kw in CATEGORY_RULES["NSFW"]:
        if kw in name_lower or kw in content:
            return "NSFW"

    # 2) Name-based classification
    for category, keywords in CATEGORY_RULES.items():
        if category == "NSFW":
            continue
        for kw in keywords:
            if kw in name_lower:
                return category

    # 3) Content-based classification
    for category, keywords in CATEGORY_RULES.items():
        if category == "NSFW":
            continue
        for kw in keywords:
            if kw in content:
                return category

    return "Misc"


# ---------------------------------------------------------
# Sorting engine with undo support
# ---------------------------------------------------------
class SortEngine:
    def __init__(self):
        self.last_moves = []  # list of (src, dst)

    def sort_perchance_directory(self, root_dir: str, log_callback, preview_only=False):
        custom_dir = os.path.join(root_dir, "custom")
        if not os.path.isdir(custom_dir):
            log_callback("❌ No 'custom' folder found.")
            return []

        log_callback(f"📂 Scanning: {custom_dir}")
        preview_data = []

        for item in os.listdir(custom_dir):
            item_path = os.path.join(custom_dir, item)
            if not os.path.isdir(item_path):
                continue

            category = classify_generator(item, item_path)
            category_folder = os.path.join(custom_dir, category)

            preview_data.append((item, category, item_path))

            if preview_only:
                continue

            if not os.path.exists(category_folder):
                os.makedirs(category_folder)
                log_callback(f"📁 Created category folder: {category}")

            new_path = os.path.join(category_folder, item)
            shutil.move(item_path, new_path)
            self.last_moves.append((new_path, item_path))  # store for undo

            log_callback(f"➡️ {item} → {category}")

        if not preview_only:
            log_callback("✅ Sorting complete!")
        return preview_data

    def undo_last_sort(self, log_callback):
        if not self.last_moves:
            log_callback("⚠️ No previous sort to undo.")
            return

        log_callback("⏪ Undoing last sort...")
        # reverse moves
        for dst, src in reversed(self.last_moves):
            try:
                shutil.move(dst, src)
                log_callback(
                    f"⬅️ {os.path.basename(dst)} → restored to original location"
                )
            except Exception as e:
                log_callback(f"❌ Failed to restore {dst}: {e}")

        self.last_moves.clear()
        log_callback("✅ Undo complete.")


# ---------------------------------------------------------
# GUI
# ---------------------------------------------------------
class PerchanceSorterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Perchance Folder Sorter (Advanced)")
        self.root.geometry("900x600")

        self.engine = SortEngine()

        # Top: folder selection
        top_frame = tk.Frame(root)
        top_frame.pack(fill=tk.X, pady=5)

        tk.Label(
            top_frame, text="Select your .Perchance folder:", font=("Arial", 11)
        ).pack(side=tk.LEFT, padx=5)

        self.path_entry = tk.Entry(top_frame, width=60)
        self.path_entry.pack(side=tk.LEFT, padx=5)

        tk.Button(top_frame, text="Browse", command=self.browse).pack(
            side=tk.LEFT, padx=5
        )

        # Buttons
        btn_frame = tk.Frame(root)
        btn_frame.pack(fill=tk.X, pady=5)

        tk.Button(btn_frame, text="Preview", command=self.preview).pack(
            side=tk.LEFT, padx=5
        )
        tk.Button(btn_frame, text="Sort Now", command=self.sort).pack(
            side=tk.LEFT, padx=5
        )
        tk.Button(btn_frame, text="Undo Last Sort", command=self.undo).pack(
            side=tk.LEFT, padx=5
        )

        # Split: preview + log
        main_frame = tk.PanedWindow(root, orient=tk.HORIZONTAL)
        main_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Preview panel
        preview_frame = tk.Frame(main_frame)
        main_frame.add(preview_frame, stretch="always")

        tk.Label(
            preview_frame,
            text="Preview Generators & Detected Categories",
            font=("Arial", 11, "bold"),
        ).pack(pady=5)

        self.tree = ttk.Treeview(
            preview_frame, columns=("name", "category", "path"), show="headings"
        )
        self.tree.heading("name", text="Folder Name")
        self.tree.heading("category", text="Category")
        self.tree.heading("path", text="Path")
        self.tree.column("name", width=200)
        self.tree.column("category", width=120)
        self.tree.column("path", width=300)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Log panel
        log_frame = tk.Frame(main_frame)
        main_frame.add(log_frame, stretch="always")

        tk.Label(log_frame, text="Log", font=("Arial", 11, "bold")).pack(pady=5)

        self.log = scrolledtext.ScrolledText(log_frame, width=50, height=20)
        self.log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def browse(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, folder)

    def log_write(self, text):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)

    def clear_preview(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def preview(self):
        root_dir = self.path_entry.get().strip()
        if not os.path.isdir(root_dir):
            messagebox.showerror("Error", "Invalid directory")
            return

        self.log_write("🔍 Generating preview...")
        self.clear_preview()
        preview_data = self.engine.sort_perchance_directory(
            root_dir, self.log_write, preview_only=True
        )

        for name, category, path in preview_data:
            self.tree.insert("", tk.END, values=(name, category, path))

        self.log_write(f"👀 Preview ready. {len(preview_data)} items listed.")

    def sort(self):
        root_dir = self.path_entry.get().strip()
        if not os.path.isdir(root_dir):
            messagebox.showerror("Error", "Invalid directory")
            return

        if not messagebox.askyesno(
            "Confirm Sort",
            "This will move folders into category subfolders.\nContinue?",
        ):
            return

        self.log_write("🔧 Starting sort...")
        self.clear_preview()
        preview_data = self.engine.sort_perchance_directory(
            root_dir, self.log_write, preview_only=False
        )

        # After sort, show new locations in preview
        for name, category, path in preview_data:
            custom_dir = os.path.join(root_dir, "custom")
            category_folder = os.path.join(custom_dir, category)
            new_path = os.path.join(category_folder, name)
            self.tree.insert("", tk.END, values=(name, category, new_path))

        self.log_write("📋 Preview updated with new locations.")

    def undo(self):
        self.engine.undo_last_sort(self.log_write)
        self.log_write("🔁 You may need to refresh preview to see restored structure.")


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = PerchanceSorterGUI(root)
    root.mainloop()
