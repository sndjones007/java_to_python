# gradio_app.py
import gradio as gr
import uuid
import os
from java_parser_javalang import JavaParser
from external_model_analyzer import ExternalModelAnalyzer
from method_doc_generator import MethodDocGenerator
from domain_doc_generator import DomainDocGenerator

# --- Helpers ---
def parse_java_source(java_source: str):
    parser = JavaParser(java_source)
    parsed = parser.parse()
    lines = getattr(parser, "lines", [])
    return parsed, lines

def _read_uploaded_file(file_obj):
    """
    Robust reader for Gradio file input. Handles file-like objects, dicts, and
    NamedString-like objects returned by different Gradio versions.
    Returns bytes.
    """
    if file_obj is None:
        return None

    # file-like (has read)
    reader = getattr(file_obj, "read", None)
    if callable(reader):
        data = reader()
        return data if isinstance(data, (bytes, bytearray)) else str(data).encode("utf-8")

    # Dict-like (e.g., {'name': path, 'data': b'...'} or {'name': 'file.java'})
    if isinstance(file_obj, dict):
        # Prefer explicit data payload
        for key in ("data", "content", "file_bytes"):
            if key in file_obj and file_obj[key] is not None:
                payload = file_obj[key]
                return payload if isinstance(payload, (bytes, bytearray)) else str(payload).encode("utf-8")
        # Fallback: try to open the provided filename
        name = file_obj.get("name")
        if isinstance(name, str) and os.path.exists(name):
            with open(name, "rb") as f:
                return f.read()

    # NamedString-like objects (has .name attribute pointing to a path)
    name = getattr(file_obj, "name", None)
    if isinstance(name, str) and os.path.exists(name):
        with open(name, "rb") as f:
            return f.read()

    # Try other common attributes
    for attr in ("data", "content", "file"):
        val = getattr(file_obj, attr, None)
        if val is not None:
            if isinstance(val, (bytes, bytearray)):
                return val
            if hasattr(val, "read"):
                d = val.read()
                return d if isinstance(d, (bytes, bytearray)) else str(d).encode("utf-8")
            return str(val).encode("utf-8")

    # Last resort: fallback to stringifying the object
    return str(file_obj).encode("utf-8")

def display_ast(parsed_data, source_lines):
    """Return a text summary of AST structure (simplified for Gradio)."""
    if "error" in parsed_data:
        return f"Parsing Error: {parsed_data['error']}"
    summary = []
    for key, value in parsed_data.items():
        if isinstance(value, list):
            summary.append(f"🏷️ {key.title()} ({len(value)} items)")
        elif isinstance(value, dict):
            summary.append(f"🏷️ {key.title()} (dict)")
    return "\n".join(summary)

def analyze_external_models(parsed_data, source_lines):
    analyzer = ExternalModelAnalyzer(parsed_data, "\n".join(source_lines))
    usages = analyzer.analyze()
    if not usages:
        return "No external models found."
    out = []
    for model, u in usages.items():
        out.append(f"📦 {model}: {len(u)} usages")
    return "\n".join(out)

def generate_method_docs(java_source):
    generator = MethodDocGenerator(java_source)
    methods = generator.list_methods()
    outputs = []
    for m in methods[:20]:
        prompts = generator.build_prompts_for_method(m["class_index"], m["method_index"])
        for idx, prompt in enumerate(prompts):
            doc = generator.run_prompt(prompt)
            outputs.append(f"🛠️ {m['class_name']}.{m['method_name']} - Chunk {idx+1}\n{doc}")
    return "\n\n".join(outputs)

def generate_model_docs(parsed_data, source_lines):
    generator = DomainDocGenerator(parsed_data, "\n".join(source_lines))
    models = generator.external_models
    outputs = []
    for model in models[:20]:
        doc = generator.run_prompt(model)
        outputs.append(f"📦 Model: {model}\n{doc}")
    return "\n\n".join(outputs)

# --- Gradio Interface ---
with gr.Blocks() as demo:
    gr.Markdown("# Java Code Tool Dashboard 🛠️")

    with gr.Tab("🚀 Parse Java"):
        file_input = gr.File(label="Upload .java file")
        parse_btn = gr.Button("Parse Java", scale=0, min_width=120)

        # Use an Accordion (collapsible section) for the AST summary similar to Streamlit's expander
        with gr.Accordion("🧩 AST Summary", open=False) as ast_section:
            ast_output = gr.Textbox(label="AST Summary (collapsed)", lines=15)

        # Use an Accordion for external models as well
        with gr.Accordion("📦 External Models", open=False) as ext_section:
            ext_output = gr.Textbox(label="External Models (collapsed)", lines=10)

        def parse_file(file_obj):
            # Robustly read uploaded content
            raw = _read_uploaded_file(file_obj)
            if raw is None:
                return "No file provided.", "No external models found.", "", {}, []
            try:
                java_source = raw.decode("utf-8")
            except Exception:
                java_source = raw.decode("utf-8", errors="replace")

            parsed, lines = parse_java_source(java_source)
            ast = display_ast(parsed, lines)
            ext = analyze_external_models(parsed, lines)
            # Return AST summary, external summary, plus states (java_source, parsed, lines)
            return ast, ext, java_source, parsed, lines

        parse_btn.click(
            parse_file,
            inputs=[file_input],
            outputs=[ast_output, ext_output,
                     gr.State(), gr.State(), gr.State()]  # store java_source, parsed, lines
        )

    with gr.Tab("📄 Create Doc"):
        run_methods_btn = gr.Button("Run All Methods")
        methods_output = gr.Textbox(label="Method Docs", lines=20)

        def run_methods(java_source):
            return generate_method_docs(java_source)

        run_methods_btn.click(run_methods, inputs=[gr.State()], outputs=methods_output)

    with gr.Tab("📦 External Models Doc"):
        run_models_btn = gr.Button("Run All Models")
        models_output = gr.Textbox(label="Model Docs", lines=20)

        def run_models(parsed, lines):
            return generate_model_docs(parsed, lines)

        run_models_btn.click(run_models, inputs=[gr.State(), gr.State()], outputs=models_output)

    with gr.Tab("🐍 Convert to Python"):
        gr.Markdown("This tab will be implemented later.")

demo.launch()
