import os
import json
from typing import List, Dict, Any, Optional, Callable
from env_config import EnvConfig
from llm_server import llm_chat
from java_parser_javalang import JavaParser
from chunker import MethodCodeChunker

# ----------------------------------------------------------------------
# Data Model for Method Documentation
# ----------------------------------------------------------------------
class MethodDoc:
    """
    Structured representation of documentation for a single Java method.
    """

    def __init__(self, class_name: str, method_name: str,
                 summary: str, parameters: list,
                 steps: list, return_desc: str):
        self.class_name = class_name
        self.method_name = method_name
        self.summary = summary
        self.parameters = parameters
        self.steps = steps
        self.return_desc = return_desc

    def to_dict(self) -> dict:
        """
        Convert the MethodDoc object into a dictionary for serialization.
        """
        return {
            "class_name": self.class_name,
            "method_name": self.method_name,
            "summary": self.summary,
            "parameters": self.parameters,
            "steps": self.steps,
            "return": self.return_desc,
        }

# ----------------------------------------------------------------------
# Prompt Loader
# ----------------------------------------------------------------------
def load_prompt_template(filename: str) -> str:
    """Load a prompt template from the PROMPT_FOLDER."""
    path = os.path.join(EnvConfig.PROMPT_FOLDER, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# ----------------------------------------------------------------------
# MethodDocGenerator class
# ----------------------------------------------------------------------
class MethodDocGenerator:
    def __init__(self, parsed_results: Dict[str, Any], source_lines: List[str]):
        """
        Initialize MethodDocGenerator with parsed results and source lines.
        
        Args:
            parsed_results: Dictionary containing parsed Java structure from JavaParser
            source_lines: List of source code lines
        """
        self.results = parsed_results
        self.source_lines = source_lines
        # Instantiate the Chunker once for reuse across methods
        self.chunker = MethodCodeChunker()
        
        if "error" in self.results:
            raise RuntimeError(f"Parsing error: {self.results['error']}")

    def _collect_classes(self, classes, collected=None):
        if collected is None:
            collected = []
        for cls in classes:
            collected.append(cls)
            # recurse into inner classes
            self._collect_classes(cls.get("inner_classes", []), collected)
        return collected

    def list_methods(self):
        """
        Return a flat list of all methods across classes and inner classes.
        Each entry: { "class_name": ..., "method_name": ..., "class_index": i, "method_index": j }
        """
        all_classes = self._collect_classes(self.results.get("classes", []))
        methods_list = []
        for ci, cls in enumerate(all_classes):
            for mi, m in enumerate(cls.get("methods", [])):
                methods_list.append({
                    "class_name": cls.get("class_name"),
                    "method_name": m.get("method_name"),
                    "class_index": ci,
                    "method_index": mi,
                })
        return methods_list

    def get_method_info(self, class_index: int, method_index: int) -> dict:
        all_classes = self._collect_classes(self.results.get("classes", []))
        if class_index >= len(all_classes):
            raise IndexError("Class index out of range")
        cls = all_classes[class_index]
        methods = cls.get("methods", [])
        if method_index >= len(methods):
            raise IndexError("Method index out of range")
        return {"class_name": cls.get("class_name"), "method_info": methods[method_index]}

    def build_prompts_for_method(self, class_index: int, method_index: int) -> List[str]:
        info = self.get_method_info(class_index, method_index)
        class_name = info["class_name"]
        method_info = info["method_info"]

        start_line = method_info.get("start_line")
        end_line = method_info.get("end_line")
        raw_code = "\n".join(self.source_lines[start_line - 1:end_line])

        chunks = self.chunker.chunk(raw_code)

        template = load_prompt_template("method_doc_prompt.txt")
        prompts = [
            template.replace("{{METHOD_CODE}}", chunk).replace("{{CLASS_NAME}}", class_name)
            for chunk in chunks
        ]
        return prompts

    def run_prompt(self, prompt: str) -> MethodDoc:
        """
        Send a single prompt to the LLM and parse the JSON output into a MethodDoc.
        """
        messages = [
            {"role": "system", "content": "You are a helpful documentation assistant."},
            {"role": "user", "content": prompt},
        ]
        output = llm_chat(messages)

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            raise RuntimeError("LLM did not return valid JSON.")

        return MethodDoc(
            class_name=data.get("class_name", ""),
            method_name=data.get("method_name", ""),
            summary=data.get("summary", ""),
            parameters=data.get("parameters", []),
            steps=data.get("steps", []),
            return_desc=data.get("return", ""),
        )

    def run_all_prompts(self, prompts: List[str], on_progress: Optional[Callable[[str], None]] = None) -> List[MethodDoc]:
        """
        Run all prompts sequentially and return a list of MethodDoc objects.
        
        Args:
            prompts: List of prompt strings
            on_progress: Optional callback function that receives status messages
            
        Returns:
            List of MethodDoc objects
        """
        docs = []
        for idx, prompt in enumerate(prompts):
            try:
                if on_progress:
                    on_progress(f"Executing prompt {idx + 1}/{len(prompts)}...")
                docs.append(self.run_prompt(prompt))
                if on_progress:
                    on_progress(f"✅ Prompt {idx + 1}/{len(prompts)} completed")
            except Exception as e:
                if on_progress:
                    on_progress(f"❌ Error on prompt {idx + 1}: {str(e)}")
                # Return error info instead of failing
                error_doc = MethodDoc(
                    class_name="",
                    method_name="",
                    return_type="",
                    summary=f"❌ Error: {str(e)}",
                    description=str(e),
                    parameters="",
                    returns="",
                    raises=""
                )
                docs.append(error_doc)
        return docs
