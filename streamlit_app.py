import uuid
import streamlit as st
from java_parser_javalang import JavaParser
from external_model_analyzer import ExternalModelAnalyzer

st.set_page_config(layout="wide", page_title="Java AST Explorer")

# --- Cached Helpers (run once, reused across reruns) ---
@st.cache_resource
def get_method_doc_generator(java_source: str):
    """Cache generator instance keyed by source code."""
    from method_doc_generator import MethodDocGenerator
    return MethodDocGenerator(java_source)

@st.cache_resource
def get_domain_doc_generator(parsed_data: dict, java_source: str):
    """Cache domain generator instance."""
    from domain_doc_generator import DomainDocGenerator
    return DomainDocGenerator(parsed_data, java_source)

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

@st.cache_data(ttl=300, show_spinner=False)
def cached_analyze(parsed_results: dict, source_text: str) -> dict:
    analyzer = ExternalModelAnalyzer(parsed_results, source_text)
    return analyzer.analyze()

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
                    with st.expander("📄 Raw Code Snippet"):
                        st.code(raw_code, language="java")
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
        # Clear cached generators on new file upload
        st.cache_resource.clear()

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

            # External models: do a quick analysis WITHOUT source code to avoid collecting raw snippets.
            with st.expander("📦 External Data Models Referenced", expanded=False):
                quick_analyzer = ExternalModelAnalyzer(parsed_data, source_code="")
                quick_usages = quick_analyzer.analyze()
                if quick_usages:
                    for model, usages in quick_usages.items():
                        with st.expander(f"📦 {model}", expanded=False):
                            st.write(f"Usages: {len(usages)}")
                            flag_key = f"show_snippets_{model}"
                            if flag_key not in st.session_state:
                                st.session_state[flag_key] = False

                            if st.button("Show code snippets", key=f"show_snippets_btn_{model}"):
                                st.session_state[flag_key] = True

                            if st.session_state.get(flag_key):
                                full_usages = cached_analyze(parsed_data, "\n".join(st.session_state['source_lines']))
                                model_usages = full_usages.get(model, [])
                                if not model_usages:
                                    st.info("No code snippets found.")
                                for u in model_usages:
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
        # Lazy init: only build methods list once, store in session
        methods_key = "create_doc_methods_cache"
        if methods_key not in st.session_state:
            java_source = "\n".join(st.session_state['source_lines'])
            generator = get_method_doc_generator(java_source)
            st.session_state[methods_key] = generator.list_methods()
            st.session_state["create_doc_generator"] = generator
        
        methods = st.session_state[methods_key]
        generator = st.session_state["create_doc_generator"]
        
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
            prompts_key = f"prompts_{m['class_name']}_{m['method_name']}"
            # only build prompts when user asks to see them
            if prompts_key not in st.session_state:
                if st.button("Show prompts", key=f"show_prompts_btn_{m['class_name']}_{m['method_name']}"):
                    st.session_state[prompts_key] = generator.build_prompts_for_method(m["class_index"], m["method_index"])

            prompts = st.session_state.get(prompts_key, [])
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
        # Lazy init: only build models list once, store in session
        models_key = "external_doc_models_cache"
        if models_key not in st.session_state:
            java_source = "\n".join(st.session_state['source_lines'])
            generator = get_domain_doc_generator(st.session_state['parsed_data'], java_source)
            st.session_state[models_key] = generator.external_models
            st.session_state["domain_doc_generator"] = generator
        
        models = st.session_state[models_key]
        generator = st.session_state["domain_doc_generator"]

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
            prompt_key = f"prompt_{model}"
            # Defer prompt build until user clicks to view
            if prompt_key not in st.session_state:
                if st.button("Show prompt", key=f"show_prompt_btn_{model}_{uuid.uuid4()}"):
                    st.session_state[prompt_key] = generator.build_prompt_for_model(model)
            
            with st.expander(f"📦 Model: {model}", expanded=False):
                if prompt_key in st.session_state:
                    prompt, usage_examples = st.session_state[prompt_key]
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
