import os
import json
from typing import Dict, Any
from env_config import EnvConfig


class JavaResultSaver:
    """
    Saves parsed Java results into structured JSON files.
    Each file corresponds to a specific entity: class, method, field, etc.
    """

    def __init__(self, output_dir: str = "parsed_results"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def _save_json(self, filename: str, data: Dict[str, Any]):
        """Helper to save a dictionary into a JSON file."""
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print(f"✅ Saved: {filepath}")

    def save_results(self, results: Dict[str, Any], source_lines: list = None):
        """
        Save parsed results into separate JSON files.
        
        Args:
            results: Dictionary with keys: packages, imports, classes, file_name, etc.
            source_lines: List of source code lines from the parsed file
        """
        if source_lines is None:
            source_lines = results.get("source_lines", [])
        
        print("\n" + "="*60)
        print("💾 Saving Parsed Java Results")
        print("="*60 + "\n")
        
        # Save packages
        for pkg in results.get("packages", []):
            fname = f"Package_{pkg['name']}.json"
            self._save_json(fname, pkg)

        # Save imports
        for imp in results.get("imports", []):
            fname = f"Import_{imp['name'].replace('.', '_')}.json"
            self._save_json(fname, imp)

        # Save classes and their members
        for cls in results.get("classes", []):
            fname = f"Class_{cls['class_name']}.json"
            self._save_json(fname, cls)

            # Save fields
            print(f"\n📌 Processing Fields for class: {cls['class_name']}")
            for field in cls.get("attributes", []):
                fname = f"Class_{cls['class_name']}_Field_{field['name']}.json"
                self._save_json(fname, field)

            # Save methods
            print(f"📌 Processing Methods for class: {cls['class_name']}")
            for method in cls.get("methods", []):
                fname = f"Class_{cls['class_name']}_Method_{method['method_name']}.json"
                self._save_json(fname, method)

            # Save inner classes/interfaces/annotations
            for inner in cls.get("inner_classes", []):
                inner_kind = inner.get("class_kind", "inner")
                fname = f"{inner_kind.capitalize()}_{inner['class_name']}.json"
                self._save_json(fname, inner)
        
        print("\n" + "="*60)
        print("✅ All results saved successfully!\n")
