import tkinter as tk
from tkinter import ttk
import json
import random

# --- PARAMETER LIBRARY (simplified from your combined visual + personality library) ---

PARAMS = {
    "characterId": [
        "char_001", "char_002", "char_003",
        "npc_merchant_01", "npc_guard_02",
        "hero_prototype_A", "villain_shadow_01"
    ],

    "name": {
        "full": ["Ari Solen", "Kael Riven", "Mira Thorne", "Juno Varr", "Selene Arctis"],
        "nickname": ["Ari", "Riv", "Thorn", "Jun", "Sel"],
        "title": [
            "Skybound Courier",
            "Wanderer of Echoes",
            "Nightglass Operative",
            "Rooftop Oracle",
            "Chrono Scribe"
        ]
    },

    "identity": {
        "age": [18, 22, 24, 29, 34, 40],
        "genderExpression": ["androgynous", "masculine", "feminine", "fluid", "neutral"],
        "species": ["human", "elf", "augmented human", "synthetic", "shifter"],
        "cultureInfluence": [
            "Nordic", "Futuristic Urban", "Old Empire",
            "Skybridge Nomad", "Deep City Industrial"
        ]
    },

    "body": {
        "height_relative": ["short", "average", "tall", "very tall"],
        "build_overall": [
            "lean athletic", "slender", "broad-shouldered",
            "compact", "runner’s build"
        ]
    },

    "face": {
        "shape": ["oval", "heart-shaped", "angular", "round", "diamond"],
        "eyes_expressionDefault": ["curious", "focused", "soft", "intense"]
    },

    "hair": {
        "length": ["short", "medium", "long", "shoulder-length"],
        "overallStyle": ["undercut", "tousled", "braided", "slicked back", "loose waves"],
        "texture": ["straight", "wavy", "curly", "coarse"]
    },

    "clothing": {
        "overallStyle": [
            "functional streetwear",
            "light sci-fi",
            "fantasy adventurer",
            "urban stealth",
            "industrial nomad"
        ]
    },

    "styleAndVibe": {
        "visualKeywords": [
            "urban explorer",
            "subtle sci-fi",
            "practical elegance",
            "quiet confidence",
            "nomadic mystic"
        ]
    },

    "corePersonality": {
        "traitsPrimary": [
            "brave", "observant", "empathetic",
            "stoic", "ambitious", "curious"
        ],
        "temperament": ["choleric", "melancholic", "phlegmatic", "sanguine"],
        "dominantMotivations": ["justice", "freedom", "power", "knowledge", "legacy"],
        "emotionalBaseline": ["calm", "tense", "cheerful", "brooding"]
    },

    "communicationStyle": {
        "tone": ["warm", "cold", "neutral", "sarcastic"],
        "directness": ["very direct", "indirect", "cryptic"]
    },

    "socialBehavior": {
        "introversionExtroversion": ["introvert", "extrovert", "ambivert"],
        "groupRole": ["leader", "strategist", "supporter", "observer"]
    },

    "valuesAndBeliefs": {
        "moralAlignment": [
            "lawful good", "neutral good",
            "chaotic neutral", "lawful evil"
        ]
    },

    "narrativeHooks": {
        "personalGoals": [
            "find artifact", "protect someone",
            "prove themselves", "escape their past"
        ]
    }
}


# --- HELPER FUNCTIONS ---

def random_choice(key_path):
    """
    key_path: tuple like ("name", "full") or ("corePersonality", "traitsPrimary")
    """
    node = PARAMS
    for k in key_path:
        node = node[k]
    return random.choice(node)


def build_character():
    """Generate a full character dict from PARAMS."""
    char = {
        "characterId": random.choice(PARAMS["characterId"]),
        "name": {
            "full": random_choice(("name", "full")),
            "nickname": random_choice(("name", "nickname")),
            "title": random_choice(("name", "title"))
        },
        "identity": {
            "age": random.choice(PARAMS["identity"]["age"]),
            "genderExpression": random.choice(PARAMS["identity"]["genderExpression"]),
            "species": random.choice(PARAMS["identity"]["species"]),
            "cultureInfluence": random.choice(PARAMS["identity"]["cultureInfluence"])
        },
        "body": {
            "height": {
                "relative": random.choice(PARAMS["body"]["height_relative"])
            },
            "build": {
                "overall": random.choice(PARAMS["body"]["build_overall"])
            }
        },
        "face": {
            "shape": random.choice(PARAMS["face"]["shape"]),
            "features": {
                "eyes": {
                    "expressionDefault": random.choice(
                        PARAMS["face"]["eyes_expressionDefault"]
                    )
                }
            }
        },
        "hair": {
            "length": random.choice(PARAMS["hair"]["length"]),
            "overallStyle": random.choice(PARAMS["hair"]["overallStyle"]),
            "texture": random.choice(PARAMS["hair"]["texture"])
        },
        "clothing": {
            "overallStyle": random.choice(PARAMS["clothing"]["overallStyle"])
        },
        "styleAndVibe": {
            "visualKeywords": [
                random.choice(PARAMS["styleAndVibe"]["visualKeywords"])
            ]
        },
        "corePersonality": {
            "traitsPrimary": [
                random.choice(PARAMS["corePersonality"]["traitsPrimary"])
            ],
            "temperament": random.choice(PARAMS["corePersonality"]["temperament"]),
            "dominantMotivations": [
                random.choice(PARAMS["corePersonality"]["dominantMotivations"])
            ],
            "emotionalBaseline": random.choice(
                PARAMS["corePersonality"]["emotionalBaseline"]
            )
        },
        "communicationStyle": {
            "tone": random.choice(PARAMS["communicationStyle"]["tone"]),
            "directness": random.choice(PARAMS["communicationStyle"]["directness"])
        },
        "socialBehavior": {
            "introversionExtroversion": random.choice(
                PARAMS["socialBehavior"]["introversionExtroversion"]
            ),
            "groupRole": random.choice(PARAMS["socialBehavior"]["groupRole"])
        },
        "valuesAndBeliefs": {
            "moralAlignment": random.choice(
                PARAMS["valuesAndBeliefs"]["moralAlignment"]
            )
        },
        "narrativeHooks": {
            "personalGoals": [
                random.choice(PARAMS["narrativeHooks"]["personalGoals"])
            ]
        }
    }
    return char


# --- TKINTER UI ---

class CharacterCreator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Character Creator (Visual + Personality)")
        self.geometry("900x700")

        self.character = build_character()

        # Notebook
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.visual_frame = ttk.Frame(notebook)
        self.personality_frame = ttk.Frame(notebook)
        self.output_frame = ttk.Frame(notebook)

        notebook.add(self.visual_frame, text="Visual")
        notebook.add(self.personality_frame, text="Personality")
        notebook.add(self.output_frame, text="JSON Output")

        self.build_visual_tab()
        self.build_personality_tab()
        self.build_output_tab()

        # Bottom controls
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=5)

        ttk.Button(bottom, text="Randomize Character",
                   command=self.randomize_character).pack(side="left")

        ttk.Button(bottom, text="Quit",
                   command=self.destroy).pack(side="right")

    # --- TAB BUILDERS ---

    def build_visual_tab(self):
        c = self.character

        def add_row(parent, label, value, row):
            ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky="w", padx=5, pady=3)
            ttk.Label(parent, text=value).grid(row=row, column=1, sticky="w", padx=5, pady=3)

        add_row(self.visual_frame, "Character ID", c["characterId"], 0)
        add_row(self.visual_frame, "Full Name", c["name"]["full"], 1)
        add_row(self.visual_frame, "Nickname", c["name"]["nickname"], 2)
        add_row(self.visual_frame, "Title", c["name"]["title"], 3)

        ttk.Separator(self.visual_frame).grid(row=4, column=0, columnspan=2, sticky="ew", pady=5)

        add_row(self.visual_frame, "Age", c["identity"]["age"], 5)
        add_row(self.visual_frame, "Gender Expression", c["identity"]["genderExpression"], 6)
        add_row(self.visual_frame, "Species", c["identity"]["species"], 7)
        add_row(self.visual_frame, "Culture Influence", c["identity"]["cultureInfluence"], 8)

        ttk.Separator(self.visual_frame).grid(row=9, column=0, columnspan=2, sticky="ew", pady=5)

        add_row(self.visual_frame, "Height (relative)", c["body"]["height"]["relative"], 10)
        add_row(self.visual_frame, "Build (overall)", c["body"]["build"]["overall"], 11)
        add_row(self.visual_frame, "Face Shape", c["face"]["shape"], 12)
        add_row(self.visual_frame, "Eyes Default Expression",
                c["face"]["features"]["eyes"]["expressionDefault"], 13)

        ttk.Separator(self.visual_frame).grid(row=14, column=0, columnspan=2, sticky="ew", pady=5)

        add_row(self.visual_frame, "Hair Length", c["hair"]["length"], 15)
        add_row(self.visual_frame, "Hair Style", c["hair"]["overallStyle"], 16)
        add_row(self.visual_frame, "Hair Texture", c["hair"]["texture"], 17)

        ttk.Separator(self.visual_frame).grid(row=18, column=0, columnspan=2, sticky="ew", pady=5)

        add_row(self.visual_frame, "Clothing Style", c["clothing"]["overallStyle"], 19)
        add_row(self.visual_frame, "Visual Keyword",
                ", ".join(c["styleAndVibe"]["visualKeywords"]), 20)

    def build_personality_tab(self):
        c = self.character

        def add_row(parent, label, value, row):
            ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky="w", padx=5, pady=3)
            ttk.Label(parent, text=value).grid(row=row, column=1, sticky="w", padx=5, pady=3)

        add_row(self.personality_frame, "Primary Trait",
                ", ".join(c["corePersonality"]["traitsPrimary"]), 0)
        add_row(self.personality_frame, "Temperament",
                c["corePersonality"]["temperament"], 1)
        add_row(self.personality_frame, "Dominant Motivation",
                ", ".join(c["corePersonality"]["dominantMotivations"]), 2)
        add_row(self.personality_frame, "Emotional Baseline",
                c["corePersonality"]["emotionalBaseline"], 3)

        ttk.Separator(self.personality_frame).grid(row=4, column=0, columnspan=2, sticky="ew", pady=5)

        add_row(self.personality_frame, "Communication Tone",
                c["communicationStyle"]["tone"], 5)
        add_row(self.personality_frame, "Communication Directness",
                c["communicationStyle"]["directness"], 6)

        ttk.Separator(self.personality_frame).grid(row=7, column=0, columnspan=2, sticky="ew", pady=5)

        add_row(self.personality_frame, "Social Intro/Extro",
                c["socialBehavior"]["introversionExtroversion"], 8)
        add_row(self.personality_frame, "Group Role",
                c["socialBehavior"]["groupRole"], 9)

        ttk.Separator(self.personality_frame).grid(row=10, column=0, columnspan=2, sticky="ew", pady=5)

        add_row(self.personality_frame, "Moral Alignment",
                c["valuesAndBeliefs"]["moralAlignment"], 11)

        ttk.Separator(self.personality_frame).grid(row=12, column=0, columnspan=2, sticky="ew", pady=5)

        add_row(self.personality_frame, "Personal Goal",
                ", ".join(c["narrativeHooks"]["personalGoals"]), 13)

    def build_output_tab(self):
        self.output_text = tk.Text(self.output_frame, wrap="none")
        self.output_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.refresh_output()

    def refresh_output(self):
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", json.dumps(self.character, indent=2))

    def randomize_character(self):
        self.character = build_character()
        # Rebuild tabs
        for child in self.visual_frame.winfo_children():
            child.destroy()
        for child in self.personality_frame.winfo_children():
            child.destroy()
        self.build_visual_tab()
        self.build_personality_tab()
        self.refresh_output()


if __name__ == "__main__":
    app = CharacterCreator()
    app.mainloop()
