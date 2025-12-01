from typing import Any, Dict, List, Set

class ExternalModelAnalyzer:
    """
    Analyzes parser results to identify external data models (types) referenced
    but not defined in the same Java file. Collects usage contexts (fields,
    parameters, return types, body references) with line numbers, snippets,
    and raw code lines (each with its own start/end line).
    """

    PRIMITIVES: Set[str] = {
        "int","long","double","float","boolean","char","byte","short","void",
        "Integer","Long","Double","Float","Boolean","Character","Byte","Short","Object"
    }
    BUILT_INS: Set[str] = {"String"}

    def __init__(self, parser_results: Dict[str, Any], source_code: str = ""):
        self.results = parser_results
        self.defined_models: Set[str] = set()
        self.external_models_usages: Dict[str, List[Dict[str, Any]]] = {}
        self.source_lines: List[str] = source_code.splitlines() if source_code else []

    def _extract_snippet(self, start_line: int, end_line: int) -> str:
        if not self.source_lines:
            return ""
        if start_line and end_line and start_line <= end_line:
            return "\n".join(self.source_lines[start_line - 1:end_line])
        return ""

    def _extract_raw_code(self, type_name: str, start_line: int, end_line: int) -> List[Dict[str, Any]]:
        """
        Return only the lines between start_line and end_line where type_name appears,
        each with its own line number metadata.
        """
        raw_code = []
        if start_line and end_line and self.source_lines:
            for idx, line in enumerate(self.source_lines[start_line - 1:end_line], start=start_line):
                if type_name in line:
                    raw_code.append({
                        "line": line.strip(),
                        "start_line": idx,
                        "end_line": idx
                    })
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
        Perform full analysis and return external models with usage contexts.
        """
        self.collect_defined_models()
        referenced_models: Set[str] = set()

        for cls in self.results.get("classes", []):
            class_name = cls.get("class_name", "")

            # Fields
            for field in cls.get("attributes", []):
                ftype = field.get("type")
                if ftype:
                    referenced_models.add(ftype)
                    start, end = field.get("start_line"), field.get("end_line")
                    usage = {
                        "context": "field",
                        "class": class_name,
                        "field_name": field.get("name"),
                        "ref_type": ftype,
                        "start_line": start,
                        "end_line": end,
                        "snippet": self._extract_snippet(start, end),
                        "raw_code": self._extract_raw_code(ftype, start, end)
                    }
                    self.external_models_usages.setdefault(ftype, []).append(usage)

            # Methods
            for method in cls.get("methods", []):
                mname = method.get("method_name", "")

                # Return type
                rtype = method.get("return_type")
                if rtype:
                    referenced_models.add(rtype)
                    start, end = method.get("start_line"), method.get("end_line")
                    usage = {
                        "context": "return_type",
                        "class": class_name,
                        "method_name": mname,
                        "ref_type": rtype,
                        "start_line": start,
                        "end_line": end,
                        "snippet": self._extract_snippet(start, end),
                        "raw_code": self._extract_raw_code(rtype, start, end)
                    }
                    self.external_models_usages.setdefault(rtype, []).append(usage)

                # Parameters
                for param in method.get("parameters", []):
                    ptype = param.get("type")
                    if ptype:
                        referenced_models.add(ptype)
                        start, end = method.get("start_line"), method.get("end_line")
                        usage = {
                            "context": "parameter",
                            "class": class_name,
                            "method_name": mname,
                            "param_name": param.get("name"),
                            "ref_type": ptype,
                            "start_line": start,
                            "end_line": end,
                            "snippet": self._extract_snippet(start, end),
                            "raw_code": self._extract_raw_code(ptype, start, end)
                        }
                        self.external_models_usages.setdefault(ptype, []).append(usage)

                # Body references
                for stmt in method.get("body", []):
                    btype = stmt.get("type")
                    if btype:
                        referenced_models.add(btype)
                        start, end = stmt.get("start_line"), stmt.get("end_line")
                        usage = {
                            "context": "body",
                            "class": class_name,
                            "method_name": mname,
                            "ref_type": btype,
                            "start_line": start,
                            "end_line": end,
                            "snippet": self._extract_snippet(start, end),
                            "raw_code": self._extract_raw_code(btype, start, end)
                        }
                        self.external_models_usages.setdefault(btype, []).append(usage)

        # Filter out defined models, primitives, built-ins
        externals = referenced_models - self.defined_models - self.PRIMITIVES - self.BUILT_INS
        return {model: self.external_models_usages.get(model, []) for model in externals}
