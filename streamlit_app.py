# streamlit_app.py
import streamlit as st
from typing import Dict, Any, List
from external_model_analyzer import ExternalModelAnalyzer  # <-- import your analyzer class

st.set_page_config(layout="wide", page_title="Java AST Explorer")

# Assuming JavaParser is available in java_parser.py
try:
    from java_parser_javalang import JavaParser
except ImportError:
    st.error("Error: Could not import JavaParser. Ensure java_parser.py is in the same directory.")
    class JavaParser:
        def __init__(self, source): pass
        def parse(self): return {"error": "Parser not available."}

# --- Core Helpers ---

def extract_raw_code_snippet(source_lines, start_line, end_line):
    """Slices the source code lines based on start_line and end_line."""
    if start_line and end_line and start_line <= end_line:
        # Streamlit stores source_lines (0-based list). Line numbers are 1-based.
        return "\n".join(source_lines[start_line - 1:end_line])
    return None

# Keys that hold lists of children and MUST be handled recursively
RECURSIVE_LIST_KEYS = ["attributes", "methods", "inner_classes", "parameters"]

# --- Refactored Summary Helpers (Specific Methods) ---

def _get_ast_item_class_summary(item: Dict[str, Any]) -> str:
    """Constructs the summary string for a Class, Interface, or Enum."""
    mod_str = _get_modifiers_string(item)
    kind = item.get("class_kind", "class")
    return f"🧩 {text_lineno(item)} {mod_str} **{kind}** `{item['class_name']}`"

def _get_ast_item_method_summary(item: Dict[str, Any]) -> str:
    """Constructs the summary string for a Method or Constructor."""
    mod_str = _get_modifiers_string(item)
    return_type = item.get("return_type", "void")
    params = item.get("parameters", [])
    
    param_list = [f"{p.get('type', '?')} {p.get('name', '?')}" for p in params]
    param_str = ", ".join(param_list)
    wrap_line = text_lineno(item)

    is_constructor = item['method_name'] == st.session_state.get('current_class_name', 'NO_CLASS_NAME')
    
    if is_constructor:
        summary = f"🏭 {wrap_line} {mod_str} **Constructor** `{item['method_name']}({param_str})`"
    else:
        summary = f"🛠️ {wrap_line} {mod_str} **{return_type}** `{item['method_name']}`({param_str})"
        
    return summary

def _get_modifiers_string(item: Dict[str, Any]) -> str:
    """Helper to format modifiers list into a string."""
    modifiers = item.get("modifiers", [])
    return f"*[{', '.join(modifiers)}]*" if modifiers else ""

def _get_ast_item_field_summary(item: Dict[str, Any]) -> str:
    """Constructs the summary string for an Attribute or Field."""
    mod_str = _get_modifiers_string(item)
    field_type = item.get("type", "?")
    name = item['name']
    value = item.get('value')
    
    val_str = f" = **{value}**" if value else ""
    
    summary = f"🔑 {text_lineno(item)} {mod_str} **{field_type}** `{name}`{val_str}"
    return summary

def _get_ast_item_summary(item: Dict[str, Any]) -> str:
    """Central dispatcher to get the concise summary for any AST item."""
    if "class_name" in item:
        return _get_ast_item_class_summary(item)
    elif "method_name" in item:
        return _get_ast_item_method_summary(item)
    elif "name" in item and "type" in item:
        return _get_ast_item_field_summary(item)
    
    return f"**{item.get('name', 'Unknown Item')}**"

def wrap_with_span(word: str, 
                   background: str = "rgb(255, 102, 102)", 
                   color: str = "white") -> str:
    return f"<span style='background-color:{background}; color:{color}; padding:2px; border-radius:3px;'>{word}</span>"

def wrap_lineno(item: Any) -> str:
    """
    Wrap line number information in a styled span.
    """
    return wrap_with_span(text_lineno(item))

def text_lineno(item: Any) -> str:
    """
    Returns line number information as plain text.
    """
    return f"({item.get('start_line', '')}, {item.get('end_line', '')})"

def _display_codeheaders(data, header="Parsed Data"):
    """
    Displays import statements.
    - Lists: Subheader showing each import.
    """
    with st.expander(header):
        if not data:
            st.info(f"No {header.lower()} found.")

        # --- Case: Displaying a list of imports (List) ---
        if isinstance(data, list):
            # Iterate over each item in the list and display it individually
            for item in data:
                st.markdown(
                    wrap_lineno(item) + f"&nbsp;&nbsp;&nbsp;&nbsp;*{item.get('name', '')}*",
                    unsafe_allow_html=True
                )
                
# --- Recursive Display Function (Main) ---
def display_ast_tree_node(data, header="Parsed Data"):
    """
    Displays AST nodes.
    - Dictionaries: Expander showing line numbers and recursive lists.
    - Lists: Subheader showing recursive items.
    """
    source_lines = st.session_state.get('source_lines', [])
    
    # --- Case 1: Displaying a single structured item (Dictionary) ---
    if isinstance(data, dict):
        summary = _get_ast_item_summary(data)
        
        # Use location data if available for a meaningful expander title
        expander_title = summary if summary != f"**{data.get('name', 'Unknown Item')}**" else f"**{header}**"
        
        with st.expander(expander_title):
            if "error" in data:
                st.error(data["error"])
                return
            
            # Save class name for constructor detection if this is a class
            if "class_name" in data:
                st.session_state['current_class_name'] = data['class_name']

            # 2. Iterate through the item's properties
            for key, value in data.items():
                
                # Skip line numbers as they are already printed
                if key not in ["attributes", "methods", "inner_classes"]:
                    continue

                # Check if the key holds a list or dict that needs recursive display
                if isinstance(value, list) and value:
                    # Check if this list is one we want to descend into (attributes, methods, parameters)
                    if key in RECURSIVE_LIST_KEYS:
                        # Recurse: display the list, which will apply the subheader and item format.
                        display_ast_tree_node(value, header=key.replace('_', ' ').title())
                        
                # Handle other nested dicts (uncommon, but covers any remaining structured data)
                elif isinstance(value, dict) and value:
                    display_ast_tree_node(value, header=key.replace('_', ' ').title())
                
                # 3. CRITICAL CHANGE: Skip ALL other simple key/value pairs (class_name, modifiers, etc.)
                # If the key is not a recursive list, not a line number, and not a nested dict, we ignore it
                # because its value is either in the header or not important enough to break the streamlined view.
                
            # Display raw code snippet
            if data.get("jtype", "") not in ("parameter", "field"):
                raw_code = extract_raw_code_snippet(source_lines,
                    data.get('start_line', ''), data.get('end_line', ''))
                if raw_code:
                    with st.expander("**`Raw Code Snippet`**"):
                        st.code(raw_code, language="java")
    
    # --- Case 2: Displaying a list of items (List) ---
    elif isinstance(data, list):
        # Only show subheader if the list isn't the root of the display
        st.subheader(header)
        
        if not data:
            st.info(f"No {header.lower()} found.")
        
        # Iterate over each item in the list and display it individually
        for item in data:
            if isinstance(item, dict):
                # Recursively call display_ast_tree_node for each item in the list.
                display_ast_tree_node(item, header=header)
            else:
                st.write(item)

# --------------------------------------------------------------------------
# --- Streamlit App Layout (Unchanged) ---
# --------------------------------------------------------------------------

st.title("Java Code Tool Dashboard 🛠️")

# Create the three required tabs
tab_parse_java, tab_create_doc, tab_external_doc, tab_convert_python = st.tabs(
    ["🚀 Parse Java", "📄 Create Doc", "📦 External Models Doc", "🐍 Convert to Python"]
)

# === TAB 1: Parse Java ===
with tab_parse_java:
    st.header("Upload and Parse Java Source File")
    
    # Initialize session state for source lines, class context, parsed data, and source content
    for key in ['source_lines', 'current_class_name', 'parsed_data', 'java_source']:
        if key not in st.session_state:
            st.session_state[key] = [] if key == 'source_lines' else '' if key == 'current_class_name' else None

    uploaded_file = st.file_uploader(
        "Choose a `.java` file",
        type="java",
        key=st.session_state.get('uploader_key', 0),
        help="Upload a Java file to parse its Abstract Syntax Tree (AST)."
    )

    # Clear State button
    if st.button("🧹 Clear State"):
        st.session_state['source_lines'] = []
        st.session_state['current_class_name'] = ''
        st.session_state['parsed_data'] = None
        st.session_state['java_source'] = None
        st.session_state['uploader_key'] = st.session_state.get('uploader_key', 0) + 1
        st.rerun()

    # If a new file is uploaded, reset state and parse
    if uploaded_file is not None:
        # Reset state when new file uploaded
        st.session_state['source_lines'] = []
        st.session_state['current_class_name'] = ''
        st.session_state['parsed_data'] = None
        st.session_state['java_source'] = None

        java_source = uploaded_file.getvalue().decode("utf-8")
        st.session_state['java_source'] = java_source

        # Parse the code using the imported JavaParser
        parser = JavaParser(java_source)
        try:
            parsed_data = parser.parse()
            st.session_state['parsed_data'] = parsed_data
            st.session_state['source_lines'] = parser.lines
        except Exception as e:
            st.error(f"Failed to run parser: {e}")
            st.session_state['parsed_data'] = {"error": str(e)}

    parsed_data = st.session_state['parsed_data']

    if parsed_data:
        if "error" in parsed_data:
            st.error(f"JAST Parsing Error: {parsed_data['error']}")
        else:
            st.success("File successfully parsed! Display is now streamlined.")

            # --- Display Parsed Data ---
            st.subheader("Organized AST Structure (Collapsible Sections)")
            
            # Display all top-level sections from the results dictionary
            _display_codeheaders(parsed_data.get("imports", []), header="📥 Imports")
            _display_codeheaders(parsed_data.get("packages", []), header="🗂️ Package")
            for key, value in parsed_data.items():
                # Skip specific keys
                if key in ("imports", "packages"):
                    continue
                if isinstance(value, (list, dict)):
                    # Use the custom function for organized, collapsible display
                    display_ast_tree_node(value, header=f"🏷️{key.replace('_', ' ').title()}")
                else:
                    st.text(f"{key.replace('_', ' ').title()}: {value}")

            # --- NEW SECTION: External Models ---
            with st.expander("📦 External Data Models Referenced", expanded=False):
                analyzer = ExternalModelAnalyzer(parsed_data, st.session_state['java_source'])
                external_models_usages = analyzer.analyze()

                if external_models_usages:
                    for model, usages in external_models_usages.items():
                        # Each external model gets its own expander
                        with st.expander(f"{model}", expanded=False):
                            if usages:
                                for u in usages:
                                    # Raw code lines
                                    raw_lines = u.get("raw_code", [])
                                    if raw_lines:
                                        st.markdown("**Raw code:**")
                                        for rc in raw_lines:
                                            # rc is a dict with line + start_line/end_line
                                            st.code(f"{rc['line']}  // line {rc['start_line']}", language="java")
                            else:
                                st.info("No usage contexts found.")
                else:
                    st.info("No external models found.")


with tab_create_doc:
    st.header("Generate Documentation")

    if st.session_state['java_source'] is None or st.session_state['parsed_data'] is None or "error" in st.session_state['parsed_data']:
        st.info("Upload and parse a Java file first in the 'Parse Java' tab.")
    else:
        st.success("Ready to generate documentation.")

        from method_doc_generator import MethodDocGenerator
        generator = MethodDocGenerator(st.session_state['java_source'])
        methods = generator.list_methods()

        st.subheader("📜 LLM Input Prompts")

        # Run All button
        run_all = st.button("▶️ Run All Methods")

        # If Run All is clicked, wrap the whole batch in spinner + progress bar
        if run_all:
            total_chunks = sum(len(generator.build_prompts_for_method(m["class_index"], m["method_index"])) for m in methods)
            progress = st.progress(0)
            completed = 0
            with st.spinner("Running all methods... please wait ⏳"):
                for m in methods:
                    prompts = generator.build_prompts_for_method(m["class_index"], m["method_index"])
                    for idx, prompt in enumerate(prompts):
                        doc = generator.run_prompt(prompt)
                        # Store result in session state so it can be displayed in the expander below
                        st.session_state[f"doc_{m['class_name']}_{m['method_name']}_{idx}"] = doc
                        completed += 1
                        progress.progress(completed / total_chunks)
            st.success("✅ Completed all prompts!")

        # Loop through methods/chunks once to build expanders
        for m in methods:
            st.markdown(f"### {m['class_name']}.{m['method_name']}")
            prompts = generator.build_prompts_for_method(m["class_index"], m["method_index"])
            for idx, prompt in enumerate(prompts):
                with st.expander(f"Chunk {idx+1}"):
                    st.code(prompt, language="text")
                    run_chunk = st.button(f"Run {m['class_name']}.{m['method_name']} - Chunk {idx+1}")
                    if run_chunk:
                        with st.spinner(f"Running {m['class_name']}.{m['method_name']} - Chunk {idx+1}... ⏳"):
                            doc = generator.run_prompt(prompt)
                            st.session_state[f"doc_{m['class_name']}_{m['method_name']}_{idx}"] = doc
                            st.success(f"✅ Finished {m['class_name']}.{m['method_name']} - Chunk {idx+1}")
                    # Show output if available (from Run All or individual run)
                    key = f"doc_{m['class_name']}_{m['method_name']}_{idx}"
                    if key in st.session_state and st.session_state[key]:
                        st.markdown("**LLM Output:**")
                        st.json(st.session_state[key].to_dict())

# === TAB 3: External Models Doc ===
with tab_external_doc:
    st.header("Generate Documentation for External Models")

    if (
        st.session_state['java_source'] is None
        or st.session_state['parsed_data'] is None
        or "error" in st.session_state['parsed_data']
    ):
        st.info("Upload and parse a Java file first in the 'Parse Java' tab.")
    else:
        st.success("Ready to generate external model documentation.")

        from domain_doc_generator import DomainDocGenerator

        generator = DomainDocGenerator(
            st.session_state['parsed_data'],
            st.session_state['java_source']
        )
        models = generator.external_models
        usages = generator.external_models_usages

        st.subheader("📜 LLM Input Prompts for External Models")

        # Run All button
        run_all = st.button("▶️ Run All Models")

        if run_all:
            total_models = len(models)
            progress = st.progress(0)
            completed = 0
            with st.spinner("Running all external models... please wait ⏳"):
                for model in models:
                    doc = generator.run_prompt(model)
                    # Store result in session state
                    st.session_state[f"doc_{model}"] = doc
                    completed += 1
                    progress.progress(completed / total_models)
            st.success("✅ Completed all external models!")

        # Loop through models once to build expanders
        for model in models:
            prompt, usage_examples = generator.build_prompt_for_model(model)
            with st.expander(f"Model: {model}", expanded=False):
                # Show usage examples collected from analyzer
                if usage_examples:
                    st.markdown("**Usage Examples:**")
                    for ex in usage_examples:
                        st.code(ex, language="java")

                # Show LLM prompt
                st.code(prompt, language="text")

                run_model = st.button(f"Run {model}")
                if run_model:
                    with st.spinner(f"Running {model}... ⏳"):
                        doc = generator.run_prompt(model)
                        st.session_state[f"doc_{model}"] = doc
                        st.success(f"✅ Finished {model}")

                # Show output if available (from Run All or individual run)
                key = f"doc_{model}"
                if key in st.session_state and st.session_state[key]:
                    st.markdown("**LLM Output:**")
                    st.json(st.session_state[key].to_dict())

# === TAB 4: Convert to Python ===
with tab_convert_python:
    st.header("Convert to Python")

    if st.session_state['java_source'] is None or st.session_state['parsed_data'] is None:
        st.info("Upload and parse a Java file first in the 'Parse Java' tab.")
    else:
        # normal doc generation
        st.info("This tab will be implemented later for code conversion features.")
