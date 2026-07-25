import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

# ---------------------------------------------------------
# CATEGORY RULES (extend freely)
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
    ],
    "Plugins": ["plugin", "framework", "kit", "tool", "router", "flags"],
    "Styles": ["style", "css", "theme"],
    "Tools": ["json", "validator", "viewer", "studio", "toolkit", "converter"],
    "Games": ["game", "dnd", "pokemon", "ant", "colony", "minecraft"],
    "NSFW": ["nsfw", "adult", "hentai", "porno", "lust"],
    "Misc": [],
}


# ---------------------------------------------------------
# CLASSIFIER
# ---------------------------------------------------------
def classify_name(name: str) -> str:
    name_lower = name.lower()
    for category, keywords in CATEGORY_RULES.items():
        for kw in keywords:
            if kw in name_lower:
                return category
    return "Misc"


# ---------------------------------------------------------
# SORTING ENGINE
# ---------------------------------------------------------
def sort_perchance_directory(root_dir: str, log_callback):
    custom_dir = os.path.join(root_dir, "custom")
    if not os.path.isdir(custom_dir):
        log_callback("❌ No 'custom' folder found.")
        return

    log_callback(f"📂 Scanning: {custom_dir}")

    for item in os.listdir(custom_dir):
        item_path = os.path.join(custom_dir, item)

        if not os.path.isdir(item_path):
            continue

        category = classify_name(item)
        category_folder = os.path.join(custom_dir, category)

        if not os.path.exists(category_folder):
            os.makedirs(category_folder)
            log_callback(f"📁 Created category folder: {category}")

        # Move folder
        new_path = os.path.join(category_folder, item)
        shutil.move(item_path, new_path)

        log_callback(f"➡️ {item} → {category}")

    log_callback("✅ Sorting complete!")


# ---------------------------------------------------------
# GUI
# ---------------------------------------------------------
class PerchanceSorterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Perchance Folder Sorter")
        self.root.geometry("700x500")

        tk.Label(root, text="Select your .Perchance folder:", font=("Arial", 12)).pack(
            pady=10
        )

        self.path_entry = tk.Entry(root, width=60)
        self.path_entry.pack()

        tk.Button(root, text="Browse", command=self.browse).pack(pady=5)
        tk.Button(root, text="Sort Now", command=self.sort).pack(pady=10)

        self.log = scrolledtext.ScrolledText(root, width=80, height=20)
        self.log.pack(pady=10)

    def browse(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, folder)

    def log_write(self, text):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)

    def sort(self):
        root_dir = self.path_entry.get().strip()
        if not os.path.isdir(root_dir):
            messagebox.showerror("Error", "Invalid directory")
            return

        self.log_write("🔍 Starting sort...")
        sort_perchance_directory(root_dir, self.log_write)


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = PerchanceSorterGUI(root)
    root.mainloop()
