"""Read-only Python architecture inspection."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "database/project_knowledge/source_inventory.json"

inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))

items = []

for entry in inventory["files"]:
    path = entry["source_path"]

    if not path.endswith(".py"):
        continue

    file_path = ROOT / path

    if not file_path.is_file() or file_path.is_symlink():
        continue

    try:
        source = file_path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=path)
    except (OSError, UnicodeError, SyntaxError) as error:
        items.append(
            {
                "path": path,
                "inspection_error": type(error).__name__,
            }
        )
        continue

    classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]

    functions = [
        node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    if (
        "agent" in path.lower()
        or "workflow" in path.lower()
        or "orchestrat" in path.lower()
        or "registry" in path.lower()
    ):
        items.append(
            {
                "path": path,
                "classes": classes,
                "functions": functions,
            }
        )

print("PROJECT ARCHITECTURE INSPECTION")
print("Relevant Python modules:", len(items))

for item in items:
    print("\nFILE:", item["path"])

    if "inspection_error" in item:
        print(" Inspection issue:", item["inspection_error"])
        continue

    print(" Classes:", ", ".join(item["classes"]) or "None")
    print(" Functions:", ", ".join(item["functions"]) or "None")

print("\nInspection completed; no database changes.")
