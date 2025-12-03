"""
FieldDocGenerator
- Similar to MethodDocGenerator but focused on fields (attributes).
- Takes parsed_results and source_lines directly (no JavaParser instantiation).
- Loads prompt template from field_doc_prompt.txt and fills placeholders:
    {CLASS_NAME}, {FIELD_NAME}, {FIELD_TYPE}, {FIELD_CODE}
- Provides:
    - list_fields() -> List[Dict] of discovered fields with indices and metadata
    - build_prompts_for_field(class_index, field_index) -> List[str]
    - run_prompt(prompt) -> FieldDoc (has to_dict())
    - run_all_prompts(prompts, callback=None) -> List[FieldDoc] (with progress callback)
"""
import os
import json
from typing import List, Dict, Any, Optional, Callable
from env_config import EnvConfig
from llm_server import llm_chat
from chunker import MethodCodeChunker


# ----------------------------------------------------------------------
# Data Model for Field Documentation
# ----------------------------------------------------------------------
class FieldDoc:
    """
    Structured representation of documentation for a single Java field.
    """

    def __init__(self, class_name: str, field_name: str, field_type: str,
                 summary: str, description: str, usage: str):
        self.class_name = class_name
        self.field_name = field_name
        self.field_type = field_type
        self.summary = summary
        self.description = description
        self.usage = usage

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the FieldDoc object into a dictionary for serialization.
        """
        return {
            "class_name": self.class_name,
            "field_name": self.field_name,
            "field_type": self.field_type,
            "summary": self.summary,
            "description": self.description,
            "usage": self.usage,
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
# FieldDocGenerator class
# ----------------------------------------------------------------------
class FieldDocGenerator:
    """Generates LLM prompts and documentation for Java field attributes."""

    def __init__(self, parsed_results: Dict[str, Any], source_lines: List[str]):
        """
        Initialize FieldDocGenerator with parsed results and source lines.
        
        Args:
            parsed_results: Dictionary containing parsed Java structure from JavaParser
            source_lines: List of source code lines
        """
        self.results = parsed_results
        self.source_lines = source_lines
        # Instantiate the Chunker once for reuse across fields
        self.chunker = MethodCodeChunker()
        
        if "error" in self.results:
            raise RuntimeError(f"Parsing error: {self.results['error']}")
        
        self._fields = self._collect_fields()
        self._prompt_template = load_prompt_template("field_doc_prompt.txt")

    def _collect_classes(self, classes, collected=None):
        """Recursively collect all classes including inner classes."""
        if collected is None:
            collected = []
        for cls in classes:
            collected.append(cls)
            # Recurse into inner classes
            self._collect_classes(cls.get("inner_classes", []), collected)
        return collected

    def _collect_fields(self) -> List[Dict[str, Any]]:
        """
        Walk parsed structure and collect fields with metadata.
        Each entry contains:
          - class_index, field_index
          - class_name, field_name, field_type
          - start_line, end_line
          - raw_code (string)
        """
        fields: List[Dict[str, Any]] = []
        all_classes = self._collect_classes(self.results.get("classes", []))
        
        for ci, cls in enumerate(all_classes):
            class_name = cls.get("class_name", "Unknown")
            attributes = cls.get("attributes", []) or []
            
            for fi, attr in enumerate(attributes):
                fname = attr.get("name", f"field{fi}")
                ftype = attr.get("type", "")
                s_line = attr.get("start_line")
                e_line = attr.get("end_line")
                raw = self._extract_raw_code_snippet(s_line, e_line)
                modifiers = attr.get("modifiers", [])
                
                fields.append({
                    "class_index": ci,
                    "field_index": fi,
                    "class_name": class_name,
                    "field_name": fname,
                    "field_type": ftype,
                    "modifiers": modifiers,
                    "start_line": s_line,
                    "end_line": e_line,
                    "raw_code": raw,
                })
        
        return fields

    def _extract_raw_code_snippet(self, start_line: Optional[int], end_line: Optional[int]) -> str:
        """Extract raw code snippet from source_lines using 1-based line numbers."""
        if not self.source_lines or not start_line or not end_line:
            return ""
        
        # Convert 1-based to 0-based indexing
        start_idx = max(0, start_line - 1)
        end_idx_exclusive = min(len(self.source_lines), end_line)
        
        if start_idx >= end_idx_exclusive:
            return ""
        
        return "\n".join(self.source_lines[start_idx:end_idx_exclusive])

    def list_fields(self) -> List[Dict[str, Any]]:
        """
        Return a flat list of all fields across classes and inner classes.
        Each entry: { "class_name": ..., "field_name": ..., "class_index": i, "field_index": j }
        """
        return self._fields

    def get_field_info(self, class_index: int, field_index: int) -> Dict[str, Any]:
        """Retrieve field information by class_index and field_index."""
        all_classes = self._collect_classes(self.results.get("classes", []))
        if class_index >= len(all_classes):
            raise IndexError("Class index out of range")
        cls = all_classes[class_index]
        attributes = cls.get("attributes", [])
        if field_index >= len(attributes):
            raise IndexError("Field index out of range")
        return {
            "class_name": cls.get("class_name", "Unknown"),
            "field_info": attributes[field_index]
        }

    def build_prompts_for_field(self, class_index: int, field_index: int) -> List[str]:
        """
        Build LLM prompts for a specific field by chunking the raw code.
        
        Args:
            class_index: Index of the class in collected classes list
            field_index: Index of the field in the class's attributes list
            
        Returns:
            List of prompts (typically one, but could be multiple if code is chunked)
        """
        info = self.get_field_info(class_index, field_index)
        class_name = info["class_name"]
        field_info = info["field_info"]

        start_line = field_info.get("start_line")
        end_line = field_info.get("end_line")
        
        # Extract raw code for the field
        raw_code = "\n".join(self.source_lines[start_line - 1:end_line])

        # Chunk the code (typically fields are short, so usually 1 chunk)
        chunks = self.chunker.chunk(raw_code)

        # Build prompts from template
        template = self._prompt_template
        prompts = [
            template.replace("{{FIELD_CODE}}", chunk)
                    .replace("{{CLASS_NAME}}", class_name)
                    .replace("{{FIELD_NAME}}", field_info.get("name", ""))
                    .replace("{{FIELD_TYPE}}", field_info.get("type", ""))
            for chunk in chunks
        ]
        return prompts

    def run_prompt(self, prompt: str) -> FieldDoc:
        """
        Send a single prompt to the LLM and parse the JSON output into a FieldDoc.
        
        Args:
            prompt: The LLM prompt string
            
        Returns:
            FieldDoc object with parsed documentation
        """
        messages = [
            {"role": "system", "content": "You are a helpful documentation assistant for Java code."},
            {"role": "user", "content": prompt},
        ]
        output = llm_chat(messages)

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            raise RuntimeError("LLM did not return valid JSON.")

        return FieldDoc(
            class_name=data.get("class_name", ""),
            field_name=data.get("field_name", ""),
            field_type=data.get("field_type", ""),
            summary=data.get("summary", ""),
            description=data.get("description", ""),
            usage=data.get("usage", ""),
        )

    def run_all_prompts(self, prompts: List[str], on_progress: Optional[Callable[[str], None]] = None) -> List[FieldDoc]:
        """
        Run all prompts sequentially and return a list of FieldDoc objects.
        
        Args:
            prompts: List of prompt strings
            on_progress: Optional callback function that receives status messages
            
        Returns:
            List of FieldDoc objects
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
                error_doc = FieldDoc(
                    class_name="",
                    field_name="",
                    field_type="",
                    summary=f"❌ Error: {str(e)}",
                    description=str(e),
                    usage=""
                )
                docs.append(error_doc)
        return docs