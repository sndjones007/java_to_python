"""
Final Java Parser using javalang (instead of jAST) for robust parsing.
- FIX: Uses the javalang token stream to reliably determine the end line number
       for multi-line structures like classes and methods.
"""

from typing import Any, Dict, List, Optional
import javalang 
import gc

class JavaParser:
    """
    Parses Java source code using the javalang library and extracts structured
    information about imports, classes, fields, and methods.
    """
    def __init__(self, java_source: str):
        self.source = java_source
        self.lines = java_source.split("\n")
        self.tokens = []  # Initialize storage for tokens
        self.reset()

    def reset(self):
        """A dedicated method to reset the object's state."""
        self.results = {"imports": [], "packages": [], "classes": []}

    # ---------------------------------------------------------
    # Helper: Location, Name, and Raw Code unwrapping (JAVALANG)
    # ---------------------------------------------------------
    
    def _get_location(self, node: Any) -> Dict[str, Optional[int]]:
        """
        FIXED: Calculates the start and end line numbers using the stored token stream.
        Handles different node types:
        - Classes/Methods: track brace nesting to find matching closing brace
        - Parameters: find the parameter name token and next delimiter (comma or closing paren)
        - Imports/Fields: find the semicolon terminator
        """
        start_position = getattr(node, "position", None)
        start_line = getattr(start_position, "line", None)
        node_type = type(node).__name__
        
        if start_line is None or not self.tokens:
            return {"start_line": start_line, "end_line": start_line}

        # ===== SPECIAL CASE: FormalParameter =====
        # Parameters don't have braces; they're in a comma/paren-delimited list.
        # Strategy: find the parameter name token, then look for the next comma or closing paren.
        if node_type == "FormalParameter":
            param_name = getattr(node, "name", None)
            if not param_name:
                return {"start_line": start_line, "end_line": start_line}
            
            # Search for the parameter name token starting from start_line
            found_name = False
            for i, token in enumerate(self.tokens):
                if token.position.line >= start_line and token.value == param_name:
                    found_name = True
                    # Look ahead for comma or closing paren to mark end of parameter
                    for j in range(i + 1, len(self.tokens)):
                        next_token = self.tokens[j]
                        if next_token.value in (',', ')'):
                            return {"start_line": start_line, "end_line": next_token.position.line}
                    # Fallback: no delimiter found, assume single-line parameter
                    return {"start_line": start_line, "end_line": start_line}
            
            # Fallback: parameter name not found in token stream
            return {"start_line": start_line, "end_line": start_line}

        # ===== DEFAULT CASE: Classes, Methods, Fields, Imports =====
        # Find the start token index by position matching
        start_index = -1
        for i, token in enumerate(self.tokens):
            if token.position == start_position:
                start_index = i
                break
        
        if start_index == -1:
            # Fallback: scan tokens for a token on start_line
            for i, token in enumerate(self.tokens):
                if token.position.line == start_line:
                    start_index = i
                    break
        
        if start_index == -1:
            return {"start_line": start_line, "end_line": start_line}

        # Track brace nesting depth to find the matching closing brace
        brace_depth = 0
        end_line = start_line
        found_opening_brace = False
        
        for i in range(start_index, len(self.tokens)):
            token = self.tokens[i]
            
            if token.value == '{':
                brace_depth += 1
                found_opening_brace = True
            elif token.value == '}':
                if found_opening_brace:
                    brace_depth -= 1
                    # When brace_depth reaches 0, we've found the matching closing brace
                    if brace_depth == 0:
                        end_line = token.position.line
                        break
            elif token.value == ';' and not found_opening_brace:
                # For simple statements (imports, fields) that don't have braces
                end_line = token.position.line
                break
        
        return {"start_line": start_line, "end_line": end_line}

    def _raw_code(self, start: Optional[int], end: Optional[int]) -> Optional[str]:
        """Slices the raw source code lines based on the start and end line numbers."""
        if start and end and start <= end:
            return "\n".join(self.lines[start - 1:end])
        return None

    def _unwrap_name(self, node: Any) -> Optional[str]:
        """Recursively extracts the string representation of a name, identifier, or value."""
        if node is None:
            return None
        if isinstance(node, str):
            return node
        
        node_type = type(node).__name__

        if hasattr(node, "name"):
            return str(node.name)
        elif hasattr(node, "member"):
            return str(node.member)
        elif hasattr(node, "value"):
            value = str(node.value)
            if value.startswith('"') and value.endswith('"'):
                return value.strip('"')
            return value
        elif hasattr(node, "qualifier"):
            if node_type == 'PackageDeclaration' or node_type == 'Import':
                return getattr(node, 'path', getattr(node, 'name', None))

        if hasattr(node, 'type') and node.type is not None:
             return self._unwrap_name(node.type)
            
        elif node_type == "VariableDeclarator":
            return getattr(node, "name", None)

        return None

    # ... (other helper methods remain unchanged)

    def _extract_modifiers(self, node: Any) -> List[str]:
        raw_modifiers = getattr(node, "modifiers", [])
        return [m.lower() for m in raw_modifiers]

    def _append_result(self, results: Dict[str, Any], key: str, data: Any):
        target_list = results.setdefault(key, [])
        if isinstance(data, list):
            target_list.extend(data)
        elif isinstance(data, dict) and data:
            target_list.append(data)
        
    def _extract_package(self, node: Any) -> Optional[Dict[str, Any]]:
        info = { "jtype": "package", "name": getattr(node, "name", None) }
        info.update(self._get_location(node))
        return info

    def _extract_import(self, node: Any) -> Dict[str, Any]:
        base_path = getattr(node, "path", None)
        is_wildcard = getattr(node, "wildcard", False)
        full_name = f"{base_path}.*" if (base_path and is_wildcard) else base_path
        info = {
            "jtype": "import", "name": full_name, "static": getattr(node, "static", False), 
            "wildcard": is_wildcard,
        }
        info.update(self._get_location(node))
        return info

    def _extract_field(self, node: Any) -> List[Dict[str, Any]]:
        results = []
        location = self._get_location(node)
        field_type = self._unwrap_name(getattr(node, "type", None))
        declarators = getattr(node, "declarators", [])
        
        for decl in declarators:
            init_value = self._unwrap_name(getattr(decl, "initializer", None))
            field_info = {
                "jtype": "field", "name": getattr(decl, "name", None), "type": field_type,
                "value": init_value, "modifiers": self._extract_modifiers(node),
            }
            field_info.update(location)
            results.append(field_info)
        return results

    def _extract_method(self, node: Any) -> Dict[str, Any]:
        params = []
        for p in getattr(node, "parameters", []):
            # 2. Get the location specifically for the parameter 'p'
            param_location = self._get_location(p)
            param_info = {
                "jtype": "parameter",
                "name": getattr(p, "name", None), 
                "type": self._unwrap_name(getattr(p, "type", None)),
            }
            param_info.update(param_location)
            params.append(param_info)
            
        method_name = getattr(node, "name", type(node).__name__) 
        return_type = self._unwrap_name(getattr(node, "return_type", None))

        method_info = {
            "jtype": "method",
            "method_name": method_name,
            "return_type": return_type,
            "modifiers": self._extract_modifiers(node),
            "parameters": params,
        }
        location = self._get_location(node)
        method_info.update(location)
        return method_info

    def _extract_interface(self, node: Any) -> Dict[str, Any]:
        """
        Extracts structured information from a javalang InterfaceDeclaration node.
        Interfaces contain method signatures (abstract methods), constants (fields), and inner types.
        """
        location = self._get_location(node)

        interface_info = {
            "jtype": "interface",
            "class_name": getattr(node, "name", None),  # Use same key as class for compatibility
            "class_kind": "interface",
            "modifiers": self._extract_modifiers(node),
            "attributes": [],  # Constants in interfaces
            "methods": [],     # Method signatures (no body)
            "inner_classes": [],
        }
        interface_info.update(location)
        
        members = getattr(node, "body", [])

        for m in members:
            if hasattr(m, 'declarations'):
                member_list = getattr(m, 'declarations', [])
            else:
                member_list = [m]
            
            for member in member_list:
                self.extract_node(member, interface_info)
            
        return interface_info

    def _extract_class(self, node: Any) -> Dict[str, Any]:
        """
        Extracts structured information from a javalang ClassDeclaration node.
        Classes contain fields, methods, constructors, and inner types.
        """
        location = self._get_location(node)

        class_info = {
            "jtype": "class",
            "class_name": getattr(node, "name", None), 
            "class_kind": type(node).__name__.lower().replace("declaration", ""),
            "modifiers": self._extract_modifiers(node),
            "attributes": [],
            "methods": [],
            "inner_classes": [],
        }
        class_info.update(location)
        
        members = getattr(node, "body", [])

        for m in members:
            if hasattr(m, 'declarations'):
                member_list = getattr(m, 'declarations', [])
            else:
                member_list = [m]
            
            for member in member_list:
                self.extract_node(member, class_info) 
            
        return class_info

    def _extract_annotation(self, node: Any) -> Dict[str, Any]:
        """
        Extracts structured information from a javalang AnnotationDeclaration node.
        Annotations contain method declarations and constant fields.
        """
        location = self._get_location(node)

        annotation_info = {
            "jtype": "annotation",
            "class_name": getattr(node, "name", None),
            "class_kind": "annotation",
            "modifiers": self._extract_modifiers(node),
            "attributes": [],
            "methods": [],
            "inner_classes": [],
        }
        annotation_info.update(location)
        
        members = getattr(node, "body", [])

        for m in members:
            if hasattr(m, 'declarations'):
                member_list = getattr(m, 'declarations', [])
            else:
                member_list = [m]
            
            for member in member_list:
                self.extract_node(member, annotation_info)
            
        return annotation_info

    # ---------------------------------------------------------
    # Central Dispatcher
    # ---------------------------------------------------------
    def extract_node(self, node: Any, results: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        The central recursive dispatcher to extract information from any javalang node.
        """
        if node is None:
            return None
        
        tname = type(node).__name__
        extracted_data = None
        result_key = None
        
        if tname == "PackageDeclaration":
            extracted_data = self._extract_package(node)
            result_key = "packages"
        
        elif tname == "Import":
            extracted_data = self._extract_import(node)
            result_key = "imports"
        
        elif tname == "InterfaceDeclaration":
            extracted_data = self._extract_interface(node)
            if results is not None:
                key = "inner_classes" if "class_kind" in results else "classes"
                self._append_result(results, key, extracted_data)
        
        elif tname == "AnnotationDeclaration":
            extracted_data = self._extract_annotation(node)
            if results is not None:
                key = "inner_classes" if "class_kind" in results else "classes"
                self._append_result(results, key, extracted_data)
        
        elif tname in ("ClassDeclaration", "EnumDeclaration"):
            extracted_data = self._extract_class(node)
            if results is not None:
                key = "inner_classes" if "class_kind" in results else "classes"
                self._append_result(results, key, extracted_data)
        
        elif tname == "FieldDeclaration":
            extracted_data = self._extract_field(node)
            result_key = "attributes"
        
        elif tname in ("MethodDeclaration", "ConstructorDeclaration"):
            extracted_data = self._extract_method(node)
            result_key = "methods"
        
        if result_key and results is not None:
            self._append_result(results, result_key, extracted_data)
        
        return extracted_data

    # ---------------------------------------------------------
    # Main parse (UPDATED to get tokens)
    # ---------------------------------------------------------
    def parse(self) -> Dict[str, Any]:
        """
        The main public method to parse the Java source code.
        NOTE: Tokens are generated first to enable accurate end line calculation.
        """
        try:
            # 1. Generate Tokens
            self.tokens = list(javalang.tokenizer.tokenize(self.source))
            
            # 2. Parse AST using the source
            tree: javalang.tree.CompilationUnit = javalang.parse.parse(self.source)
        except javalang.tokenizer.LexerError as e:
            return {"error": f"Javalang Lexer Error: {e}"}
        except javalang.parser.ParserError as e:
            return {"error": f"Javalang Parser Error: {e}"}
        except Exception as e:
            return {"error": f"General Parsing Error: {e}"}

        self.reset()
        
        # Extract AST components
        package_node = getattr(tree, "package", None)
        if package_node: self.extract_node(package_node, self.results)

        for imp in getattr(tree, "imports", []): self.extract_node(imp, self.results)

        for unit in getattr(tree, "types", []): self.extract_node(unit, self.results)

        try: del tree
        except Exception: pass
        gc.collect()

        return self.results


# ----------------------------------------------------------------------
# Test Execution and Verification
# ----------------------------------------------------------------------
if __name__ == "__main__":
    
    from pprint import pprint

    MOCK_JAVA_CODE = """
package com.example.demo;

import java.util.List;
import static java.lang.System.out;
import java.io.File;
import java.time.*;

public class Person {
    private String name = "Default";
    private final int MAX_AGE = 120;
    public List<String> hobbies;
    
    public Person(String name) {
        this.name = name;
        this.hobbies = List.of("Coding", "Reading");
    }
    
    public void greet(String message) {
        out.println("Hello, " + name + "! " + message);
    }
    
    public int getAge(LocalDate birthDate) {
        return Period.between(birthDate, LocalDate.now()).getYears();
    }
}
"""
    # Line map:
    # 9: public class Person { <--- Class Start
    # 26: } <--- Class End

    results = {}
    
    print(f"Loading code from mock source.")

    try:
        parser = JavaParser(MOCK_JAVA_CODE)
        results = parser.parse()
        
    except Exception as e:
        print(f"An error occurred during parsing: {e}")
        
    # --- Verification Checks ---
    if results and "error" not in results:
        print("\n--- Verification Results ---")
        
        # 1. Check Class (Line 9-26)
        class_info = results["classes"][0]
        # This assertion should now pass due to the token-based fix!
        assert class_info["start_line"] == 9
        assert class_info["end_line"] == 26 
        print(f"✅ Class: {class_info['class_name']} (Line {class_info['start_line']}-{class_info['end_line']})")
        
        # 2. Check Method (e.g., greet is Line 18-20)
        methods = class_info["methods"]
        method_info = methods[1] 
        assert method_info["start_line"] == 19
        assert method_info["end_line"] == 21
        print(f"✅ Found {len(methods)} methods. (e.g., '{method_info['method_name']}' Line {method_info['start_line']}-{method_info['end_line']})")

        print("\n--- Detailed Output ---")
        pprint(results)
    else:
        print(f"\n🚫 Verification checks skipped. Error: {results.get('error', 'Unknown Error')}")