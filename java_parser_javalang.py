"""
Final Java Parser using javalang (instead of jAST) for robust parsing.
- Does not include 'raw_code' in the output JSON.
- Extraction relies only on start_line.
- Handles complex nested parameter structures.
"""

from typing import Any, Dict, List, Optional
import javalang # <-- Switched from jast to javalang
import os
from pprint import pprint

class JavaParser:
    """
    Parses Java source code using the javalang library and extracts structured
    information about imports, classes, fields, and methods.
    """
    def __init__(self, java_source: str):
        self.source = java_source
        self.lines = java_source.split("\n")
        self.reset()

    def reset(self):
        """A dedicated method to reset the object's state."""
        self.results = {"imports": [], "packages": [], "classes": []}

    # ---------------------------------------------------------
    # Helper: Location, Name, and Raw Code unwrapping (JAVALANG)
    # ---------------------------------------------------------
    
    def _get_location(self, node: Any) -> Dict[str, Optional[int]]:
        """
        Attempts to find both start and end line numbers for a node.
        javalang only provides start_line, so we heuristically compute end_line
        by scanning the source code for matching braces or statement terminators.
        """
        start_position = getattr(node, "position", None)
        start_line = getattr(start_position, "line", None)
        end_line = start_line

        if start_line is None:
            return {"start_line": None, "end_line": None}

        # Heuristic: look at the source starting from start_line
        code_slice = self.lines[start_line - 1:]
        brace_count = 0
        found_end = False

        for idx, line in enumerate(code_slice, start=start_line):
            # Count braces to detect block boundaries
            brace_count += line.count("{")
            brace_count -= line.count("}")

            # For declarations with bodies (class, method, constructor)
            if brace_count == 0 and ("{" in self.lines[start_line - 1]):
                end_line = idx
                found_end = True
                break

            # For single-line statements (imports, fields)
            if ";" in line and brace_count == 0 and idx >= start_line:
                end_line = idx
                found_end = True
                break

        if not found_end:
            # fallback: assume single-line node
            end_line = start_line

        return {"start_line": start_line, "end_line": end_line}

    def _raw_code(self, start: Optional[int], end: Optional[int]) -> Optional[str]:
        """
        Slices the raw source code lines based on the start and end line numbers.
        (Kept for internal use, though not used in the final output structure).
        """
        if start and end and start <= end:
            return "\n".join(self.lines[start - 1:end])
        return None

    def _unwrap_name(self, node: Any) -> Optional[str]:
        """
        Recursively extracts the string representation of a name, identifier,
        or value from a javalang node.
        """
        if node is None:
            return None
        if isinstance(node, str):
            return node
        
        node_type = type(node).__name__

        # Javalang Specific Logic
        if hasattr(node, "name"):
            return str(node.name)
        elif hasattr(node, "member"): # Used for MethodInvocation like System.out.println
            return str(node.member)
        elif hasattr(node, "value"): # Used for Literals/Primitives
            # Unquote string literals
            value = str(node.value)
            if value.startswith('"') and value.endswith('"'):
                return value.strip('"')
            return value
        elif hasattr(node, "qualifier"): # Used for QualifiedName (Package/Import)
            # Qualifiers/Names are often stored as an iterable of identifiers
            if node_type == 'PackageDeclaration' or node_type == 'Import':
                # Javalang stores the fully qualified name as a string on the node.
                return getattr(node, 'path', getattr(node, 'name', None))

        # Fallback for complex types (e.g., ReferenceType)
        if hasattr(node, 'type') and node.type is not None:
             # Recursively unwrap the type node
            return self._unwrap_name(node.type)
            
        # For VariableDeclarator, the name is directly accessible
        elif node_type == "VariableDeclarator":
            return getattr(node, "name", None)

        return None

    # ---------------------------------------------------------
    # Helper: Modifiers and Results Appending
    # ---------------------------------------------------------
    def _extract_modifiers(self, node: Any) -> List[str]:
        """
        Extracts the string names (lowercased type name) for all modifiers 
        associated with a declaration node (Class, Method, Field).
        """
        # Javalang stores modifiers as a list of strings (e.g., ['public', 'static'])
        raw_modifiers = getattr(node, "modifiers", [])
        return [m.lower() for m in raw_modifiers]

    def _append_result(self, results: Dict[str, Any], key: str, data: Any):
        """
        Handles appending a single dictionary or extending a list of dictionaries
        to the specified key in the results structure.
        """
        target_list = results.setdefault(key, [])
        if isinstance(data, list):
            target_list.extend(data)
        elif isinstance(data, dict) and data:
            target_list.append(data)
        
    # ---------------------------------------------------------
    # Extractors (private helper methods)
    # ---------------------------------------------------------
    
    def _extract_package(self, node: Any) -> Optional[Dict[str, Any]]:
        """Extracts structured information from a javalang PackageDeclaration node."""
        if node is None:
            return None
        # Javalang stores the full name as 'name'
        info = {
            "jtype": "package",
            "name": getattr(node, "name", None)
        }
        info.update(self._get_location(node))
        return info

    def _extract_import(self, node: Any) -> Dict[str, Any]:
        """Extracts structured information from a javalang Import node."""
        base_path = getattr(node, "path", None)
        is_wildcard = getattr(node, "wildcard", False)

        # Append .* if wildcard is true
        full_name = f"{base_path}.*" if (base_path and is_wildcard) else base_path

        info = {
            "jtype": "import",
            "name": full_name,
            "static": getattr(node, "static", False),
            "wildcard": is_wildcard,
        }
        info.update(self._get_location(node))
        return info

    def _extract_field(self, node: Any) -> List[Dict[str, Any]]:
        """Extracts structured information for all fields in a FieldDeclaration node."""
        results = []
        location = self._get_location(node)
        
        # Javalang: Type is on the FieldDeclaration node
        field_type = self._unwrap_name(getattr(node, "type", None))
        
        # Javalang: Declarators are VariableDeclarator nodes
        declarators = getattr(node, "declarators", [])
        
        for decl in declarators:
            # Javalang uses 'initializer' for the field value
            init_value = self._unwrap_name(getattr(decl, "initializer", None))
            
            field_info = {
                "jtype": "field",
                # Name is directly on VariableDeclarator
                "name": getattr(decl, "name", None), 
                "type": field_type,
                "value": init_value, 
                "modifiers": self._extract_modifiers(node),
            }
            field_info.update(location)
            results.append(field_info)
        return results

    def _extract_method(self, node: Any) -> Dict[str, Any]:
        """Extracts structured information from a javalang MethodDeclaration or ConstructorDeclaration node."""
        params = []
        
        # Javalang parameters are directly on the node
        for p in getattr(node, "parameters", []):
            params.append({
                "jtype": "parameter",
                # Parameter name is direct attribute
                "name": getattr(p, "name", None), 
                # Type is a node that needs unwrapping
                "type": self._unwrap_name(getattr(p, "type", None)),
            })
            
        location = self._get_location(node)

        # Method name is 'name' for MethodDeclaration and null for ConstructorDeclaration
        method_name = getattr(node, "name", type(node).__name__) 
        # Return type is 'return_type' for MethodDeclaration and null for ConstructorDeclaration
        return_type = self._unwrap_name(getattr(node, "return_type", None))

        method_info = {
            "jtype": "method",
            "method_name": method_name,
            "return_type": return_type,
            "modifiers": self._extract_modifiers(node),
            "parameters": params,
        }
        method_info.update(location)
        return method_info

    def _extract_class(self, node: Any) -> Dict[str, Any]:
        """Extracts structured information from a javalang TypeDeclaration (Class, Interface, Enum, Annotation) node."""
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
        
        # Javalang structure: members are found in the 'body' attribute, which is a list.
        members = getattr(node, "body", [])

        # Iterate through members (FieldDeclaration, MethodDeclaration, etc.)
        for m in members:
            # Check if 'm' is an iterable of statements/declarations (e.g., in BlockStatement)
            if hasattr(m, 'declarations'):
                 member_list = getattr(m, 'declarations', [])
            else:
                member_list = [m]
            
            for member in member_list:
                self.extract_node(member, class_info) 
            
        return class_info

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
        
        # Javalang node types:
        if tname == "PackageDeclaration": # Equivalent to jAST's Package
            extracted_data = self._extract_package(node)
            result_key = "packages"
        
        elif tname == "Import":
            extracted_data = self._extract_import(node)
            result_key = "imports"
            
        elif tname in ("ClassDeclaration", "InterfaceDeclaration", "EnumDeclaration", "AnnotationDeclaration"):
            # These are Javalang's TypeDeclaration nodes
            extracted_data = self._extract_class(node)
            if results is not None:
                # Check if we are inside a class (for inner_classes) or at the top level (for classes)
                key = "inner_classes" if "class_kind" in results else "classes"
                self._append_result(results, key, extracted_data)
                
        elif tname == "FieldDeclaration": # Equivalent to jAST's Field/Variable
            extracted_data = self._extract_field(node)
            result_key = "attributes"
        
        elif tname in ("MethodDeclaration", "ConstructorDeclaration"):
            extracted_data = self._extract_method(node)
            result_key = "methods"
        
        # VariableDeclarator is a child of FieldDeclaration; it's handled in _extract_field.
        # Other nodes (e.g., literal, assignment) are ignored at this top level.
        
        if result_key and results is not None:
            self._append_result(results, result_key, extracted_data)
        
        return extracted_data

    # ---------------------------------------------------------
    # Main parse
    # ---------------------------------------------------------
    def parse(self) -> Dict[str, Any]:
        """
        The main public method to parse the Java source code using javalang.
        """
        try:
            # javalang.parse.parse returns the CompilationUnit node
            tree: javalang.tree.CompilationUnit = javalang.parse.parse(self.source)
        except javalang.tokenizer.LexerError as e:
            return {"error": f"Javalang Lexer Error: {e}"}
        except javalang.parser.ParserError as e:
            # This handles the complex expression parsing issue
            return {"error": f"Javalang Parser Error: {e}"}
        except Exception as e:
            # Handle general exceptions
            return {"error": f"General Parsing Error: {e}"}

        self.reset()
        
        # Extract AST components from javalang's CompilationUnit structure
        
        # 1. Package
        package_node = getattr(tree, "package", None)
        if package_node:
            self.extract_node(package_node, self.results)

        # 2. Imports
        for imp in getattr(tree, "imports", []):
            self.extract_node(imp, self.results)

        # 3. Type Declarations (Classes, Interfaces, etc.)
        for unit in getattr(tree, "types", []): # Javalang uses 'types' for top-level declarations
            self.extract_node(unit, self.results)

        return self.results


# ----------------------------------------------------------------------
# Test Execution and Verification (UNCHANGED LOGIC)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    
    # NOTE: Path uses a RAW string (r"...") for Windows compatibility
    TEST_FILE_NAME = r"D:\SUBHADEEP\TCS AI Batch 2\java_doc_python\data\javacode\Person.java"
    results = {}
    code_from_file = None
    
    # Check if the test file exists before proceeding
    if not os.path.exists(TEST_FILE_NAME):
        print(f"🚫 Error: Test file '{TEST_FILE_NAME}' not found.")
        exit(1)

    print(f"Loading code from existing file: {TEST_FILE_NAME}")

    try:
        # 1. Read the code from the existing file
        with open(TEST_FILE_NAME, "r", encoding="utf-8") as f:
            code_from_file = f.read()

        # 2. Execute the parser using code loaded from the file
        parser = JavaParser(code_from_file)
        results = parser.parse()
        
    except Exception as e:
        print(f"An error occurred during file reading or parsing: {e}")
        
    # --- Verification Checks ---
    if results and code_from_file:
        
        if "error" in results:
            print(f"🚫 Fatal Parsing Error: {results['error']}")
            print("Verification checks cannot proceed.")
            exit(1)
            
        print("\n--- Verification Results ---")
        
        # 1. Check main results structure
        assert "packages" in results, "Key 'packages' is missing."
        assert "imports" in results, "Key 'imports' is missing."
        assert "classes" in results, "Key 'classes' is missing."
        print("✅ Basic structure keys exist (packages, imports, classes).")

        # 2. Check Package 
        if results["packages"]:
            package_name = results["packages"][0]["name"]
            assert package_name == "com.example.demo"
            print(f"✅ Package name: {package_name}")
        
        # 3. Check Imports
        assert len(results["imports"]) == 4
        print(f"✅ Found {len(results['imports'])} imports.")

        # 4. Check Class
        class_info = results["classes"][0]
        assert class_info["class_name"] == "Person"
        assert class_info["class_kind"] == "class"
        print(f"✅ Main class name: {class_info['class_name']}")
        
        # 5. Check Fields (Attributes)
        attributes = class_info["attributes"]
        assert len(attributes) == 3
        print(f"✅ Found {len(attributes)} attributes.")
        
        # 6. Check Methods
        methods = class_info["methods"]
        # Expected: Constructor (1) + greet (1) + updateDetails (1) + getAge (1) + displayInfo (1) = 5
        assert len(methods) == 5 
        print(f"✅ Found {len(methods)} methods (including constructor).")
        
        # --- Simplified Verification Footer ---
        print("\n--- Detailed Output ---")
        print(f"## Extracted AST Structure for {TEST_FILE_NAME}")
        pprint(results)
    else:
        print("\n🚫 Verification checks skipped due to an execution error or empty results.")