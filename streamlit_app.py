import uuid
import streamlit as st
from typing import Dict, Any
from external_model_analyzer import ExternalModelAnalyzer

st.set_page_config(layout="wide", page_title="Java AST Explorer")

try:
    from java_parser_javalang import JavaParser
except ImportError:
    st.error("Error: Could not import JavaParser.")
    class JavaParser:
        def __init__(self, source): pass
        def parse(self): return {"error": "Parser not available."}
        @property
        def lines(self): return []

# --- Helpers ---
def extract_raw_code_snippet(source_lines, start_line, end_line):
    if start_line and end_line and start_line <= end_line:
        return "\n".join(source_lines[start_line - 1:end_line])
    return None

@st.cache_data
def parse_java_source(java_source: str):
    parser = JavaParser(java_source)
    parsed = parser.parse()
    lines = getattr(parser, "lines", [])
    return parsed, lines

def display_ast_tree_node(data, header="Parsed Data", depth=0, max_depth=2):
    """Display AST nodes with limited recursion for responsiveness, with icons."""
    source_lines = st.session_state.get('source_lines', [])
    if isinstance(data, dict):
        if "class_name" in data:
            summary = f"🧩 {data.get('class_kind','class')} {data['class_name']}"
        elif "method_name" in data:
            if data['method_name'] == st.session_state.get('current_class_name'):
                summary = f"🏭 Constructor {data['method_name']}"
            else:
                summary = f"🛠️ Method {data['method_name']}"
        elif "name" in data and "type" in data:
            summary = f"🔑 Field {data['name']}"
        else:
            summary = data.get("name", "Unknown")

        with st.expander(f"{header}: {summary}", expanded=False):
            if depth < max_depth:
                for key, value in data.items():
                    if isinstance(value, (list, dict)):
                        display_ast_tree_node(value, header=key.title(), depth=depth+1, max_depth=max_depth)
            if data.get("start_line") and data.get("end_line"):
                raw_code = extract_raw_code_snippet(source_lines, data["start_line"], data["end_line"])
                if raw_code:
                    st.expander("📄 Raw Code Snippet").code(raw_code, language="java")
    elif isinstance(data, list):
        for item in data[:50]:
            display_ast_tree_node(item, header=header, depth=depth, max_depth=max_depth)
        if len(data) > 50:
            st.info(f"... {len(data)-50} more items not shown for performance")

# --- Layout ---
st.title("Java Code Tool Dashboard 🛠️")
tab_parse_java, tab_create_doc, tab_external_doc, tab_convert_python = st.tabs(
    ["🚀 Parse Java", "📄 Create Doc", "📦 External Models Doc", "🐍 Convert to Python"]
)

# === TAB 1: Parse Java ===
with tab_parse_java:
    st.header("Upload and Parse Java Source File")

    for key, default in [
        ("source_lines", []),
        ("current_class_name", ""),
        ("parsed_data", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    uploaded_file = st.file_uploader("Choose a `.java` file", type="java")

    if uploaded_file is not None:
        java_source = uploaded_file.getvalue().decode("utf-8")
        with st.spinner("Parsing Java source... ⏳"):
            parsed_data, source_lines = parse_java_source(java_source)
        st.session_state['parsed_data'] = parsed_data
        st.session_state['source_lines'] = source_lines

    parsed_data = st.session_state.get('parsed_data')
    if parsed_data:
        if "error" in parsed_data:
            st.error(f"Parsing Error: {parsed_data['error']}")
        else:
            st.success("File successfully parsed!")
            with st.spinner("Rendering AST structure... ⏳"):
                for key, value in parsed_data.items():
                    if isinstance(value, (list, dict)):
                        display_ast_tree_node(value, header=f"🏷️ {key.title()}")

            with st.expander("📦 External Data Models Referenced", expanded=False):
                analyzer = ExternalModelAnalyzer(parsed_data, "\n".join(st.session_state['source_lines']))
                with st.spinner("Analyzing external models... ⏳"):
                    external_models_usages = analyzer.analyze()
                if external_models_usages:
                    for model, usages in external_models_usages.items():
                        with st.expander(f"📦 {model}", expanded=False):
                            for u in usages:
                                for rc in u.get("raw_code", [])[:10]:
                                    st.code(f"{rc['line']}  // line {rc['start_line']}", language="java")
                else:
                    st.info("No external models found.")

# === TAB 2: Create Documentation ===
with tab_create_doc:
    st.header("Generate Documentation")
    if not st.session_state.get('parsed_data'):
        st.info("Upload and parse a Java file first.")
    else:
        from method_doc_generator import MethodDocGenerator
        java_source = "\n".join(st.session_state['source_lines'])
        with st.spinner("Collecting methods... ⏳"):
            generator = MethodDocGenerator(java_source)
            methods = generator.list_methods()

        run_all = st.button("▶️ Run All Methods")
        if run_all:
            total_chunks = sum(len(generator.build_prompts_for_method(m["class_index"], m["method_index"])) for m in methods)
            progress = st.progress(0)
            completed = 0
            with st.spinner("Running all methods... ⏳"):
                for m in methods:
                    prompts = generator.build_prompts_for_method(m["class_index"], m["method_index"])
                    for idx, prompt in enumerate(prompts):
                        doc = generator.run_prompt(prompt)
                        st.session_state[f"doc_{m['class_name']}_{m['method_name']}_{idx}"] = doc
                        completed += 1
                        progress.progress(completed / total_chunks)
            st.success("✅ Completed all prompts!")

        for m in methods[:20]:
            st.markdown(f"### 🛠️ {m['class_name']}.{m['method_name']}")
            prompts = generator.build_prompts_for_method(m["class_index"], m["method_index"])
            for idx, prompt in enumerate(prompts):
                with st.expander(f"Chunk {idx+1}"):
                    st.code(prompt, language="text")
                    run_chunk = st.button(
                        f"Run {m['class_name']}.{m['method_name']} - Chunk {idx+1}",
                        key=f"run_{m['class_name']}_{m['method_name']}_{idx}_{uuid.uuid4()}"
                    )
                    if run_chunk:
                        with st.spinner("Running chunk... ⏳"):
                            doc = generator.run_prompt(prompt)
                            st.session_state[f"doc_{m['class_name']}_{m['method_name']}_{idx}"] = doc
                            st.success("✅ Finished")
                    key = f"doc_{m['class_name']}_{m['method_name']}_{idx}"
                    if key in st.session_state:
                        st.json(st.session_state[key].to_dict())

# === TAB 3: External Models Doc ===
with tab_external_doc:
    st.header("Generate Documentation for External Models")
    if not st.session_state.get('parsed_data'):
        st.info("Upload and parse a Java file first.")
    else:
        from domain_doc_generator import DomainDocGenerator
        java_source = "\n".join(st.session_state['source_lines'])
        generator = DomainDocGenerator(st.session_state['parsed_data'], java_source)
        models = generator.external_models

        run_all = st.button("▶️ Run All Models")
        if run_all:
            progress = st.progress(0)
            completed = 0
            with st.spinner("Running all models... ⏳"):
                for model in models:
                    doc = generator.run_prompt(model)
                    st.session_state[f"doc_{model}"] = doc
                    completed += 1
                    progress.progress(completed / len(models))
            st.success("✅ Completed all models!")

        for model in models[:20]:
            prompt, usage_examples = generator.build_prompt_for_model(model)
            with st.expander(f"📦 Model: {model}", expanded=False):
                for ex in usage_examples[:10]:
                    st.code(ex, language="java")
                st.code(prompt, language="text")
                run_model = st.button(f"Run {model}", key=f"run_{model}_{uuid.uuid4()}")
                if run_model:
                    with st.spinner("Running model... ⏳"):
                        doc = generator.run_prompt(model)
                        st.session_state[f"doc_{model}"] = doc
                        st.success("✅ Finished")
                if f"doc_{model}" in st.session_state:
                    st.json(st.session_state[f"doc_{model}"].to_dict())

# === TAB 4: Convert to Python ===
with tab_convert_python:
    st.header("Convert to Python")
    st.info("This tab will be implemented later.")
