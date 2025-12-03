from typing import Any, Dict, List, Set, Optional
import re
import gc

class ExternalModelAnalyzer:
    """
    Analyze parser results to find usages of external models/classes.
    Optimized to cap raw matches and release large in-memory buffers.
    """
    PRIMITIVES: Set[str] = {
        "int", "long", "double", "float", "boolean", "byte", "short", "char", "void", "String"
    }
    BUILT_INS: Set[str] = {"List", "Map", "Set", "Optional", "HashMap", "ArrayList"}

    def __init__(self, parser_results: Dict[str, Any], source_code: str = ""):
        self.results = parser_results
        self.defined_models: Set[str] = set()
        self.external_models_usages: Dict[str, List[Dict[str, Any]]] = {}
        # Keep source lines but allow release after analysis
        self.source_lines: List[str] = source_code.splitlines() if source_code else []
        # Cap how many raw-code matches are kept per type to avoid unbounded memory usage
        self.MAX_RAW_MATCHES = 200

    def _extract_snippet(self, start_line: Optional[int], end_line: Optional[int]) -> str:
        """
        Return the snippet between 1-based start_line and end_line (inclusive).
        Converts to 0-based slice indices for self.source_lines.
        """
        if not self.source_lines:
            return ""
        if not start_line or not end_line:
            return ""
        # convert 1-based inclusive to 0-based slice [start_idx:end_idx_exclusive]
        start_idx = max(0, start_line - 1)
        end_idx_exclusive = min(len(self.source_lines), end_line)  # end_line is inclusive (1-based)
        if start_idx >= end_idx_exclusive:
            return ""
        return "\n".join(self.source_lines[start_idx:end_idx_exclusive])

    def _extract_raw_code(self, type_name: str, start_line: Optional[int], end_line: Optional[int]) -> List[Dict[str, Any]]:
        """
        Return only the lines between start_line and end_line (both 1-based, inclusive)
        where type_name appears, each with its own line number metadata.
        Caps matches to MAX_RAW_MATCHES.
        """
        raw_code: List[Dict[str, Any]] = []
        if not (start_line and end_line and self.source_lines):
            return raw_code

        # Convert 1-based inclusive to 0-based slice indices
        start_idx = max(0, start_line - 1)
        end_idx_exclusive = min(len(self.source_lines), end_line)
        if start_idx >= end_idx_exclusive:
            return raw_code

        count = 0
        # iterate through the slice and collect lines containing the type_name
        for rel_idx, line in enumerate(self.source_lines[start_idx:end_idx_exclusive], start=start_idx):
            if type_name in line:
                # rel_idx is 0-based index; convert back to 1-based line number for metadata
                line_no = rel_idx + 1
                raw_code.append({
                    "line": line.strip(),
                    "start_line": line_no,
                    "end_line": line_no
                })
                count += 1
                if count >= self.MAX_RAW_MATCHES:
                    break
        return raw_code

    def collect_defined_models(self):
        def collect_class_names(classes: List[Dict[str, Any]]):
            for cls in classes:
                if "class_name" in cls and cls["class_name"]:
                    self.defined_models.add(cls["class_name"])
                collect_class_names(cls.get("inner_classes", []))
        collect_class_names(self.results.get("classes", []))

    def analyze(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Walk parser results to find external model references and return a mapping
        { model_name: [usages...] }.

        Releases the source_lines buffer after analysis to free memory.
        """
        # Collect defined models (classes / interfaces / enums)
        self.collect_defined_models()

        # Helper regex to extract potential type names from signatures/returns
        type_regex = re.compile(r"\b([A-Z][A-Za-z0-9_<>]*)\b")

        # scan class attributes and methods for referenced types
        for cls in self.results.get("classes", []):
            class_name = cls.get("class_name")
            # attributes
            for attr in cls.get("attributes", []):
                t = attr.get("type")
                if not t:
                    continue
                s_line = attr.get("start_line")
                e_line = attr.get("end_line")
                for match in type_regex.findall(str(t)):
                    self._record_usage(match, {
                        "location": f"{class_name}.attribute",
                        "line_info": {"start": s_line, "end": e_line},
                        "raw_code": self._extract_raw_code(match, s_line, e_line)
                    })

            # methods
            for m in cls.get("methods", []):
                s_line = m.get("start_line")
                e_line = m.get("end_line")
                
                # return type
                rt = m.get("return_type")
                if rt:
                    for match in type_regex.findall(str(rt)):
                        self._record_usage(match, {
                            "location": f"{class_name}.method.return",
                            "line_info": {"start": s_line, "end": e_line},
                            "raw_code": self._extract_raw_code(match, s_line, e_line)
                        })
                
                # parameters and their usages inside method body
                for p in m.get("parameters", []):
                    pt = p.get("type")
                    ps = p.get("start_line")
                    pe = p.get("end_line")
                    if pt:
                        for match in type_regex.findall(str(pt)):
                            # Extract raw code for parameter declaration
                            param_raw = self._extract_raw_code(match, ps, pe)
                            
                            # ADDED: Extract usages of this type inside the method body (s_line to e_line)
                            method_body_raw = self._extract_raw_code(match, s_line, e_line)
                            
                            # Combine: param declaration + method body usages
                            combined_raw = param_raw + method_body_raw
                            
                            # Deduplicate by line number to avoid showing same line twice
                            seen_lines = set()
                            unique_raw = []
                            for rc in combined_raw:
                                line_key = (rc["start_line"], rc["line"])
                                if line_key not in seen_lines:
                                    seen_lines.add(line_key)
                                    unique_raw.append(rc)
                            
                            self._record_usage(match, {
                                "location": f"{class_name}.method.param",
                                "line_info": {"start": ps, "end": pe},
                                "raw_code": unique_raw
                            })

        # Filter out defined models, primitives, built-ins
        referenced_models = set(self.external_models_usages.keys())
        externals = referenced_models - self.defined_models - self.PRIMITIVES - self.BUILT_INS
        results = {model: self.external_models_usages.get(model, []) for model in externals}

        # Release large buffers to reduce peak memory usage
        try:
            self.source_lines = []
            gc.collect()
        except Exception:
            pass

        return results

    def _record_usage(self, model_name: str, usage: Dict[str, Any]) -> None:
        if not model_name:
            return
        lst = self.external_models_usages.setdefault(model_name, [])
        # avoid collecting empty raw_code lists excessively
        if usage.get("raw_code"):
            lst.append(usage)
        else:
            lst.append(usage)
