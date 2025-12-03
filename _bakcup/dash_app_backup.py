# dash_app.py
import base64
import json
import dash
from dash import Dash, dcc, html, Input, Output, State, MATCH, callback_context

import dash_bootstrap_components as dbc

from java_parser_javalang import JavaParser
from external_model_analyzer import ExternalModelAnalyzer
from method_doc_generator import MethodDocGenerator
from field_doc_generator import FieldDocGenerator

# --- Helpers ---
def parse_java_source(java_source: str):
    parser = JavaParser(java_source)
    parsed = parser.parse()
    lines = getattr(parser, "lines", [])
    return parsed, lines

def extract_raw_code_snippet(source_lines, start_line, end_line):
    if start_line and end_line and start_line <= end_line:
        return "\n".join(source_lines[start_line - 1:end_line])
    return None

def build_imports_expander(parsed_data):
    imports = parsed_data.get("imports", [])
    if not imports:
        return dbc.AccordionItem("No imports found.", title="📥 Imports")
    items = [html.Div(f"{imp.get('name','')} (lines {imp.get('start_line','')}–{imp.get('end_line','')})")
             for imp in imports]
    return dbc.AccordionItem(items, title="📥 Imports")

def build_packages_expander(parsed_data):
    packages = parsed_data.get("packages", [])
    if not packages:
        return dbc.AccordionItem("No packages found.", title="🗂️ Packages")
    items = [html.Div(f"{pkg.get('name','')} (lines {pkg.get('start_line','')}–{pkg.get('end_line','')})")
             for pkg in packages]
    return dbc.AccordionItem(items, title="🗂️ Packages")

def get_type_icon_and_label(class_kind: str) -> tuple:
    """
    Returns icon and label for a given class_kind.
    """
    if class_kind == "interface":
        return "🔌", "Interface"
    elif class_kind == "annotation":
        return "📌", "Annotation"
    elif class_kind == "enum":
        return "📋", "Enum"
    else:
        return "🧩", "Class"

def build_fields_accordion(fields, source_lines):
    """
    Build accordion for fields/attributes of a type.
    """
    field_items = []
    for f in fields:
        raw_code = extract_raw_code_snippet(source_lines, f.get('start_line'), f.get('end_line'))
        field_items.append(
            dbc.AccordionItem([
                html.H6(f"🔑 {f.get('type','?')} {f.get('name','?')}"),
                html.Pre(raw_code or "", style={"backgroundColor": "#f8f9fa", "padding": "10px"})
            ], title=f"🔑 Field {f.get('name','?')} (lines {f.get('start_line','?')}–{f.get('end_line','?')})")
        )
    return dbc.Accordion(field_items, start_collapsed=True) if field_items else html.Div("No fields")

def build_methods_accordion(methods, source_lines):
    """
    Build accordion for methods of a type.
    """
    method_items = []
    for m in methods:
        raw_code = extract_raw_code_snippet(source_lines, m.get('start_line'), m.get('end_line'))
        method_items.append(
            dbc.AccordionItem([
                html.H6(f"🛠️ {m.get('method_name','?')}"),
                html.Pre(raw_code or "", style={"backgroundColor": "#f8f9fa", "padding": "10px"})
            ], title=f"🛠️ Method {m.get('method_name','?')} (lines {m.get('start_line','?')}–{m.get('end_line','?')})")
        )
    return dbc.Accordion(method_items, start_collapsed=True) if method_items else html.Div("No methods")

def build_inner_classes_accordion(inner_classes):
    """
    Build accordion for inner classes/interfaces/annotations.
    """
    inner_items = []
    if inner_classes:
        for inner in inner_classes:
            inner_kind = inner.get("class_kind", "class")
            inner_icon, _ = get_type_icon_and_label(inner_kind)
            inner_items.append(
                html.Div(f"{inner_icon} {inner.get('class_name', 'Unknown')} ({inner_kind})")
            )
    return dbc.Accordion([
        dbc.AccordionItem(inner_items, title="Inner Types")
    ], start_collapsed=True) if inner_items else html.Div("No inner types")

def build_type_item(typ, source_lines):
    """
    Build a single accordion item for a type (class, interface, annotation, enum).
    """
    class_kind = typ.get("class_kind", "class")
    icon, label = get_type_icon_and_label(class_kind)
    
    fields = typ.get("attributes", [])
    fields_acc = build_fields_accordion(fields, source_lines)
    
    methods = typ.get("methods", [])
    methods_acc = build_methods_accordion(methods, source_lines)
    
    inner_classes = typ.get("inner_classes", [])
    inner_acc = build_inner_classes_accordion(inner_classes)
    
    return dbc.AccordionItem([
        html.H5(f"{icon} {label} {typ.get('class_name','Unknown')}"),
        html.P(f"Modifiers: {', '.join(typ.get('modifiers', []))}" if typ.get('modifiers') else ""),
        html.H6("Fields:"),
        fields_acc,
        html.H6("Methods:"),
        methods_acc,
        html.H6("Inner Types:"),
        inner_acc
    ], title=f"{icon} {typ.get('class_name','Unknown')}")

def build_types_expander(parsed_data, source_lines):
    """
    Generic builder for classes, interfaces, and annotations.
    Displays all type declarations (ClassDeclaration, InterfaceDeclaration, AnnotationDeclaration).
    """
    types_list = parsed_data.get("classes", [])
    if not types_list:
        return dbc.AccordionItem("No types found.", title="🧩 Types")

    type_items = [build_type_item(typ, source_lines) for typ in types_list]

    # Wrap all type AccordionItems under a single "🧩 Types" AccordionItem
    types_accordion = dbc.Accordion(type_items, start_collapsed=True)
    return dbc.AccordionItem(types_accordion, title="🧩 Types")

def build_attr_doc_expander(parsed_data, source_lines, source_text):
    """
    Build the Types accordion for the Attributes Document Generator tab.
    - Reuses parsed_data and source_lines
    - Uses MethodDocGenerator to build LLM prompts for methods
    - Uses FieldDocGenerator to build LLM prompts for fields
    - Adds a "Generate Documentation" button for each method and each field, and
      a dedicated output placeholder (pattern-matching id) to show results.
    """
    if not parsed_data:
        return dbc.AccordionItem("No parsed data available.", title="🧩 Types for Docs")

    # Prepare generator and mapping of prompts per (class_name, method_name)
    method_prompts_map = {}
    try:
        method_generator = MethodDocGenerator(parsed_data, source_lines or [])
        methods_list = method_generator.list_methods()
        for m in methods_list:
            c = m.get("class_name")
            mn = m.get("method_name")
            prompts = method_generator.build_prompts_for_method(m["class_index"], m["method_index"])
            method_prompts_map.setdefault((c, mn), []).extend(prompts)
    except Exception as e:
        print(f"Error initializing MethodDocGenerator: {e}")
        method_prompts_map = {}

    # Prepare generator and mapping of prompts per (class_name, field_name)
    field_prompts_map = {}
    try:
        field_generator = FieldDocGenerator(parsed_data, source_lines or [])
        fields_list = field_generator.list_fields()
        for f in fields_list:
            c = f.get("class_name")
            fn = f.get("field_name")
            prompts = field_generator.build_prompts_for_field(f["class_index"], f["field_index"])
            field_prompts_map.setdefault((c, fn), []).extend(prompts)
    except Exception as e:
        print(f"Error initializing FieldDocGenerator: {e}")
        field_prompts_map = {}

    type_items = []
    for typ in parsed_data.get("classes", []):
        class_kind = typ.get("class_kind", "class")
        icon, label = get_type_icon_and_label(class_kind)
        class_name = typ.get('class_name', 'Unknown')
        title = f"{icon} {class_name}"

        # Fields: each field becomes an AccordionItem with LLM prompt + Generate button + output placeholder
        field_items = []
        for f in typ.get("attributes", []):
            fn = f.get("name", "?")
            ft = f.get("type", "?")
            
            # Get field LLM prompt from FieldDocGenerator
            field_prompts = field_prompts_map.get((class_name, fn), [])
            prompt_blocks = []
            if not field_prompts:
                prompt_blocks = [html.Pre("", style={"backgroundColor": "#f8f9fa", "padding": "8px", "minHeight": "64px"})]
            else:
                for prompt in field_prompts:
                    prompt_blocks.append(html.Pre(prompt, style={"backgroundColor": "#f8f9fa", "padding": "8px", "whiteSpace": "pre-wrap"}))
            
            field_items.append(
                dbc.AccordionItem(
                    [
                        html.Div([
                            html.B(f"{fn} : {ft}"),
                            html.Br(),
                            html.H6("LLM Prompt"),
                            html.Div(prompt_blocks),
                            dbc.Button(
                                "📤 Generate Documentation",
                                id={"type": "generate-field", "class": class_name, "field": fn},
                                color="success",
                                size="sm",
                                className="mt-2 mb-2"
                            ),
                            # Spinner container for field (hidden by default)
                            dbc.Spinner(
                                html.Div(
                                    id={"type": "field-spinner", "class": class_name, "field": fn},
                                    style={"display": "none"}
                                ),
                                color="success",
                                size="sm",
                                type="border",
                                fullscreen=False
                            ),
                            # Output container for field
                            html.Div(
                                id={"type": "field-doc-output", "class": class_name, "field": fn},
                                style={"marginTop": "12px"}
                            )
                        ])
                    ],
                    title=f"🔑 {fn} : {ft} (lines {f.get('start_line','?')}–{f.get('end_line','?')})"
                )
            )
        fields_acc = dbc.Accordion(field_items, start_collapsed=True) if field_items else dbc.AccordionItem([html.Div("No fields")], title="🔑 Fields")

        # Methods: show LLM prompts (one or more chunks) as code blocks plus generate button + output container
        method_items = []
        for m in typ.get("methods", []):
            mn = m.get("method_name", "?")
            prompts = method_prompts_map.get((class_name, mn), [])
            prompt_blocks = []
            if not prompts:
                prompt_blocks = [html.Pre("", style={"backgroundColor": "#f8f9fa", "padding": "8px", "minHeight": "64px"})]
            else:
                for idx, p in enumerate(prompts):
                    prompt_blocks.append(html.Pre(p, style={"backgroundColor": "#f8f9fa", "padding": "8px", "whiteSpace": "pre-wrap"}))
            method_body = [
                html.H6("LLM Prompt"),
                html.Div(prompt_blocks),
                dbc.Button(
                    "📤 Generate Documentation",
                    id={"type": "generate-method", "class": class_name, "method": mn},
                    color="info",
                    size="sm",
                    className="mt-2 mb-2"
                ),
                # Spinner container for method (hidden by default)
                dbc.Spinner(
                    html.Div(
                        id={"type": "method-spinner", "class": class_name, "method": mn},
                        style={"display": "none"}
                    ),
                    color="info",
                    size="sm",
                    type="border",
                    fullscreen=False
                ),
                # Output container for method
                html.Div(
                    id={"type": "method-doc-output", "class": class_name, "method": mn},
                    style={"marginTop": "12px"}
                )
            ]
            method_items.append(dbc.AccordionItem(method_body, title=f"🛠️ {mn} (lines {m.get('start_line','?')}–{m.get('end_line','?')})"))

        methods_acc = dbc.Accordion(method_items, start_collapsed=True) if method_items else dbc.AccordionItem([html.Div("No methods")], title="🛠️ Methods")

        # Assemble single type item
        inner = [
            html.H5(f"{icon} {label} {class_name}"),
            html.P(f"Modifiers: {', '.join(typ.get('modifiers', []))}" if typ.get('modifiers') else ""),
            html.H6("Fields:"),
            fields_acc,
            html.H6("Methods:"),
            methods_acc
        ]
        type_items.append(dbc.AccordionItem(inner, title=title))

    types_accordion = dbc.Accordion(type_items, start_collapsed=True) if type_items else dbc.AccordionItem("No types found.", title="🧩 Types")
    return dbc.AccordionItem(dbc.Accordion(type_items, start_collapsed=True), title="🧩 Types")

# --- Dash App ---
app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True
)
app.title = "Java to Documentation to Python 🛠️"

# Use a centered container with margins
app.layout = dbc.Container(
    [
        # Global Header
        html.H1("Java to Documentation to Python 📚🐍", className="text-center mb-4 mt-4", style={"color": "#2c3e50"}),
        html.Hr(),
        
        # Stores to persist parsed results across tabs
        dcc.Store(id="parsed-store"),
        dcc.Store(id="source-lines-store"),
        dcc.Store(id="source-text-store"),
        dcc.Store(id="progress-store", data={"current": 0, "total": 0, "status": ""}),
        dcc.Store(id="completed-docs-store", data={}),
        dcc.Store(id="progress-messages-store", data=[]),  # NEW: Store progress messages
        dcc.Interval(id="progress-interval", interval=500, disabled=True),

        # Tabs
        dcc.Tabs(id="main-tabs", value="tab-1", children=[
            # Tab 1: Java Parser
            dcc.Tab(label="🚀 Java Parser", value="tab-1", children=[
                dbc.Container([
                    html.H2("Java Source Parser", className="mt-4 mb-4"),
                    dcc.Upload(
                        id="upload-java",
                        children=html.Div(["Drag and Drop or Select a .java file"]),
                        multiple=False,
                        style={
                            "border": "2px dashed #007bff",
                            "padding": "20px",
                            "marginBottom": "20px",
                            "textAlign": "center",
                            "borderRadius": "5px",
                            "backgroundColor": "#f8f9fa"
                        }
                    ),
                    # Loading spinner + message
                    dbc.Spinner(
                        html.Div(id="loading-spinner", children=""),
                        color="primary",
                        size="lg",
                        type="border",
                        fullscreen=False
                    ),
                    dbc.Accordion(id="ast-accordion", start_collapsed=True, className="mb-4"),
                    html.Div(id="ext-output")
                ], fluid=False, style={"marginLeft": "40px", "marginRight": "40px"})
            ]),
            
            # Tab 2: Attributes Document Generator
            dcc.Tab(label="📄 Attributes Document Generator", value="tab-2", children=[
                dbc.Container([
                    html.H2("Attributes Document Generator", className="mt-4 mb-4"),
                    html.P("Reuses parsed Java file to build LLM inputs for methods. Fields currently show empty inputs."),
                    
                    # Run All Documentation Section
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("🚀 Batch Documentation Generation", className="card-title"),
                            html.P("Click below to generate documentation for all methods and fields at once.", className="card-text"),
                            dbc.Button(
                                "⚡ Run All Documentation",
                                id="run-all-docs-btn",
                                color="primary",
                                size="lg",
                                className="mb-3"
                            ),
                            # Progress bar container
                            html.Div(
                                id="progress-container",
                                style={"display": "none", "marginTop": "15px"}
                            ),
                            # Progress status text
                            html.Div(
                                id="progress-status",
                                style={"marginTop": "10px", "fontSize": "0.9em", "color": "#666"}
                            )
                        ])
                    ], className="mb-4"),
                    
                    html.Div(id="attr-doc-container")
                ], fluid=False, style={"marginLeft": "40px", "marginRight": "40px"})
            ])
        ])
    ],
    fluid=False,
    style={"marginLeft": "20px", "marginRight": "20px"}
)

# --- Callbacks ---
@app.callback(
    [Output("ast-accordion", "children"),
     Output("ext-output", "children"),
     Output("loading-spinner", "children"),
     Output("parsed-store", "data"),
     Output("source-lines-store", "data"),
     Output("source-text-store", "data")],
    Input("upload-java", "contents"),
    State("upload-java", "filename")
)
def parse_file(contents, filename):
    if contents is None:
        return [], "", "", None, None, None

    # Show loading message
    loading_message = html.Div([
        html.P("🔄 Parsing Java file...", className="text-center mt-3 mb-3"),
    ])
    try:
        decoded = base64.b64decode(contents.split(",")[1]).decode("utf-8")
        parsed, lines = parse_java_source(decoded)

        # Build expanders
        imports_exp = build_imports_expander(parsed)
        packages_exp = build_packages_expander(parsed)
        types_exp = build_types_expander(parsed, lines)

        accordion_children = [imports_exp, packages_exp, types_exp]

        # --- External models accordion ---
        analyzer = ExternalModelAnalyzer(parsed, decoded)
        usages = analyzer.analyze()
        if not usages:
            ext_section = dbc.AccordionItem("No external models found.", title="📦 External Models")
        else:
            model_items = []
            for model, u in usages.items():
                usage_blocks = []
                # Count total raw_code snippets across all usages (raw_code is a list of snippet dicts)
                raw_code_count = sum(len(usage.get("raw_code", [])) for usage in u)
                
                for usage in u:
                    for rc in usage.get("raw_code", []):
                        usage_blocks.append(
                            html.Pre(
                                f"{rc.get('line','')}  // line {rc.get('start_line','?')}",
                                style={"backgroundColor": "#f8f9fa", "padding": "6px"}
                            )
                        )
                model_items.append(
                    dbc.AccordionItem(
                        html.Div([
                            html.H6(f"📦 {model}"),
                            html.P(f"Usages: {raw_code_count}"),
                            html.Div(usage_blocks)
                        ]),
                        title=f"📦 {model}"
                    )
                )
            ext_section = dbc.AccordionItem(
                dbc.Accordion(model_items, start_collapsed=True),
                title="📦 External Models"
            )

        # Clear loading message on success and store parsed results for other tabs
        return accordion_children, dbc.Accordion([ext_section], start_collapsed=True), "", parsed, lines, decoded

    except Exception as e:
        error_message = html.Div([
            dbc.Alert(f"❌ Error parsing file: {str(e)}", color="danger", className="mt-3")
        ])
        return [], "", error_message, None, None, None

@app.callback(
    Output("attr-doc-container", "children"),
    Input("parsed-store", "data"),
    State("source-lines-store", "data"),
    State("source-text-store", "data")
)
def render_attr_doc(parsed_data, source_lines, source_text):
    """
    Renders the Attributes Document Generator content using stored parsed data.
    """
    if not parsed_data:
        return dbc.Alert("Upload and parse a Java file in the 'Java Parser' tab first.", color="info")
    try:
        types_item = build_attr_doc_expander(parsed_data, source_lines or [], source_text or "")
        return dbc.Accordion([types_item], start_collapsed=True)
    except Exception as e:
        return dbc.Alert(f"Error building attribute docs UI: {e}", color="danger")

# ===== RUN ALL DOCUMENTATION CALLBACK =====
@app.callback(
    [Output("progress-store", "data"),
     Output("progress-interval", "disabled"),
     Output("progress-container", "children"),
     Output("progress-container", "style"),
     Output("progress-status", "children"),
     Output("run-all-docs-btn", "disabled"),
     Output("completed-docs-store", "data"),
     Output("progress-messages-store", "data")],
    Input("run-all-docs-btn", "n_clicks"),
    Input("progress-interval", "n_intervals"),
    State("parsed-store", "data"),
    State("source-lines-store", "data"),
    State("progress-store", "data"),
    State("completed-docs-store", "data"),
    State("progress-messages-store", "data"),
    prevent_initial_call=True
)
def manage_batch_documentation(n_clicks, n_intervals, parsed_data, source_lines, current_progress_data, completed_docs, progress_messages):
    """
    Combined callback to manage batch documentation generation.
    Stores completed docs and progress messages in stores.
    """
    triggered = callback_context.triggered
    if not triggered:
        raise dash.exceptions.PreventUpdate
    
    trigger_id = triggered[0]["prop_id"].split(".")[0]
    
    # TRIGGER 1: Button Click - Initialize batch processing
    if trigger_id == "run-all-docs-btn":
        try:
            method_gen = MethodDocGenerator(parsed_data, source_lines or [])
            field_gen = FieldDocGenerator(parsed_data, source_lines or [])
            
            all_methods = method_gen.list_methods()
            all_fields = field_gen.list_fields()
            
            total_items = len(all_methods) + len(all_fields)
            
            if total_items == 0:
                return (
                    {"current": 0, "total": 0, "status": ""},
                    True,
                    html.Div([dbc.Alert("No methods or fields to process.", color="info")]),
                    {"display": "block", "marginTop": "15px"},
                    html.Div([html.P("No items found.", style={"color": "#666"})]),
                    False,
                    {},
                    []  # NEW: Empty messages
                )
            
            progress_data = {
                "current": 0,
                "total": total_items,
                "status": "Starting batch generation...",
                "all_methods": all_methods,
                "all_fields": all_fields,
                "method_idx": 0,
                "field_idx": 0
            }
            
            progress_bar = dbc.Progress(
                value=0,
                striped=True,
                animated=True,
                color="info",
                style={"height": "25px"}
            )
            
            progress_container = html.Div([
                progress_bar,
                html.P("0% Complete", className="mt-2", style={"color": "#007bff", "fontWeight": "bold"})
            ])
            
            status_text = html.Div([
                html.P("Starting batch generation...")
            ], style={"color": "#666"})
            
            return (
                progress_data,
                False,
                progress_container,
                {"display": "block", "marginTop": "15px"},
                status_text,
                True,
                {},
                []  # NEW: Reset messages
            )
            
        except Exception as e:
            print(f"Error initializing batch: {e}")
            error_container = html.Div([
                dbc.Alert(f"❌ Error: {str(e)}", color="danger")
            ])
            return (
                {"current": 0, "total": 0, "status": ""},
                True,
                error_container,
                {"display": "block", "marginTop": "15px"},
                html.Div([html.P(f"Error: {str(e)[:100]}", style={"color": "red"})]),
                False,
                {},
                [f"❌ Error: {str(e)}"]  # NEW: Store error message
            )
    
    # TRIGGER 2: Progress Interval - Process items one by one
    elif trigger_id == "progress-interval":
        if not current_progress_data or current_progress_data.get("total", 0) == 0:
            raise dash.exceptions.PreventUpdate
        
        try:
            current = current_progress_data.get("current", 0)
            total = current_progress_data.get("total", 0)
            all_methods = current_progress_data.get("all_methods", [])
            all_fields = current_progress_data.get("all_fields", [])
            method_idx = current_progress_data.get("method_idx", 0)
            field_idx = current_progress_data.get("field_idx", 0)
            
            method_gen = MethodDocGenerator(parsed_data, source_lines or [])
            field_gen = FieldDocGenerator(parsed_data, source_lines or [])
            
            # Initialize messages list if not already
            if not progress_messages:
                progress_messages = []
            
            # Process one method
            if method_idx < len(all_methods):
                try:
                    m = all_methods[method_idx]
                    class_idx = m.get("class_index")
                    method_idx_val = m.get("method_index")
                    method_name = m.get("method_name")
                    class_name = m.get("class_name")
                    
                    # Define progress callback that stores messages
                    def method_progress(msg):
                        timestamp = len(progress_messages) + 1
                        full_msg = f"[{class_name}.{method_name}] {msg}"
                        progress_messages.append(full_msg)
                        print(full_msg)
                    
                    prompts = method_gen.build_prompts_for_method(class_idx, method_idx_val)
                    docs = method_gen.run_all_prompts(prompts, on_progress=method_progress)
                    
                    doc_key = f"method_{class_name}_{method_name}"
                    completed_docs[doc_key] = {
                        "type": "method",
                        "class": class_name,
                        "method": method_name,
                        "docs": [doc.to_dict() if hasattr(doc, 'to_dict') else str(doc) for doc in docs]
                    }
                    
                    current += 1
                    status = f"✅ Method: {class_name}.{method_name} (✔ {current}/{total})"
                    
                    current_progress_data["current"] = current
                    current_progress_data["method_idx"] = method_idx + 1
                    current_progress_data["status"] = status
                    
                except Exception as e:
                    print(f"Error processing method: {e}")
                    error_msg = f"❌ Method: {class_name}.{method_name} - Error: {str(e)}"
                    progress_messages.append(error_msg)
                    current += 1
                    status = f"❌ Method: {class_name}.{method_name} - Error: {str(e)[:50]}"
                    current_progress_data["current"] = current
                    current_progress_data["method_idx"] = method_idx + 1
                    current_progress_data["status"] = status
            
            # Process one field
            elif field_idx < len(all_fields):
                try:
                    f = all_fields[field_idx]
                    class_idx = f.get("class_index")
                    field_idx_val = f.get("field_index")
                    field_name = f.get("field_name")
                    class_name = f.get("class_name")
                    
                    # Define progress callback that stores messages
                    def field_progress(msg):
                        timestamp = len(progress_messages) + 1
                        full_msg = f"[{class_name}.{field_name}] {msg}"
                        progress_messages.append(full_msg)
                        print(full_msg)
                    
                    prompts = field_gen.build_prompts_for_field(class_idx, field_idx_val)
                    docs = field_gen.run_all_prompts(prompts, on_progress=field_progress)
                    
                    doc_key = f"field_{class_name}_{field_name}"
                    completed_docs[doc_key] = {
                        "type": "field",
                        "class": class_name,
                        "field": field_name,
                        "docs": [doc.to_dict() if hasattr(doc, 'to_dict') else str(doc) for doc in docs]
                    }
                    
                    current += 1
                    status = f"✅ Field: {class_name}.{field_name} (✔ {current}/{total})"
                    
                    current_progress_data["current"] = current
                    current_progress_data["field_idx"] = field_idx + 1
                    current_progress_data["status"] = status
                    
                except Exception as e:
                    print(f"Error processing field: {e}")
                    error_msg = f"❌ Field: {class_name}.{field_name} - Error: {str(e)}"
                    progress_messages.append(error_msg)
                    current += 1
                    status = f"❌ Field: {class_name}.{field_name} - Error: {str(e)[:50]}"
                    current_progress_data["current"] = current
                    current_progress_data["field_idx"] = field_idx + 1
                    current_progress_data["status"] = status
            
            progress_pct = int((current / total) * 100)
            
            # Check if done
            if current >= total:
                progress_bar = dbc.Progress(
                    value=100,
                    striped=True,
                    animated=False,
                    color="success",
                    style={"height": "25px"}
                )
                
                progress_container = html.Div([
                    progress_bar,
                    html.P("✅ Documentation generation complete!", className="mt-2", style={"color": "green", "fontWeight": "bold"})
                ])
                
                status_text = html.Div([
                    html.P(f"✅ Processed {total} items ({len(all_methods)} methods, {len(all_fields)} fields)")
                ], style={"color": "green"})
                
                current_progress_data["current"] = 0
                current_progress_data["total"] = 0
                
                # Format progress messages for display
                message_items = []
                for msg in progress_messages[-10:]:  # Show last 10 messages
                    if "✅" in msg or "Executing" in msg:
                        color = "#28a745"
                    elif "❌" in msg:
                        color = "#dc3545"
                    else:
                        color = "#666"
                    
                    message_items.append(
                        html.Div(
                            msg,
                            style={
                                "padding": "6px 12px",
                                "marginBottom": "4px",
                                "borderRadius": "3px",
                                "backgroundColor": "#f8f9fa",
                                "borderLeft": f"3px solid {color}",
                                "fontSize": "0.9em",
                                "fontFamily": "monospace",
                                "color": color
                            }
                        )
                    )
                
                status_display = html.Div([
                    html.Div(status_text),  # Your existing status_text
                    html.H6("📋 Execution Log:", style={"marginTop": "12px", "marginBottom": "8px", "color": "#333"}) if message_items else None,
                    html.Div(
                        message_items,
                        style={
                            "maxHeight": "200px",
                            "overflowY": "auto",
                            "backgroundColor": "#fafbfc",
                            "padding": "10px",
                            "borderRadius": "4px",
                            "border": "1px solid #e1e4e8"
                        }
                    ) if message_items else None
                ])
                
                return (
                    current_progress_data,
                    True,
                    progress_container,
                    {"display": "block", "marginTop": "15px"},
                    status_display,
                    False,
                    completed_docs,
                    progress_messages  # NEW: Return accumulated messages
                )
            
            else:
                progress_bar = dbc.Progress(
                    value=progress_pct,
                    striped=True,
                    animated=True,
                    color="info",
                    style={"height": "25px"}
                )
                
                progress_container = html.Div([
                    progress_bar,
                    html.P(f"{progress_pct}% Complete", className="mt-2", style={"color": "#007bff", "fontWeight": "bold"})
                ])
                
                status_text = html.Div([
                    html.P(current_progress_data.get("status", f"Processing... {current}/{total}"))
                ], style={"color": "#666"})
                
                # Format progress messages for display
                message_items = []
                for msg in progress_messages[-10:]:  # Show last 10 messages
                    if "✅" in msg or "Executing" in msg:
                        color = "#28a745"
                    elif "❌" in msg:
                        color = "#dc3545"
                    else:
                        color = "#666"
                    
                    message_items.append(
                        html.Div(
                            msg,
                            style={
                                "padding": "6px 12px",
                                "marginBottom": "4px",
                                "borderRadius": "3px",
                                "backgroundColor": "#f8f9fa",
                                "borderLeft": f"3px solid {color}",
                                "fontSize": "0.9em",
                                "fontFamily": "monospace",
                                "color": color
                            }
                        )
                    )
                
                status_display = html.Div([
                    html.Div(status_text),  # Your existing status_text
                    html.H6("📋 Execution Log:", style={"marginTop": "12px", "marginBottom": "8px", "color": "#333"}) if message_items else None,
                    html.Div(
                        message_items,
                        style={
                            "maxHeight": "200px",
                            "overflowY": "auto",
                            "backgroundColor": "#fafbfc",
                            "padding": "10px",
                            "borderRadius": "4px",
                            "border": "1px solid #e1e4e8"
                        }
                    ) if message_items else None
                ])
                
                return (
                    current_progress_data,
                    False,
                    progress_container,
                    {"display": "block", "marginTop": "15px"},
                    status_display,
                    True,
                    completed_docs,
                    progress_messages  # NEW: Return accumulated messages
                )
        
        except Exception as e:
            print(f"Progress update error: {e}")
            error_msg = f"❌ Progress error: {str(e)}"
            progress_messages.append(error_msg)
            error_container = html.Div([
                dbc.Alert(f"❌ Error: {str(e)}", color="danger")
            ])
            error_status = html.Div([
                html.P(f"Error: {str(e)[:100]}", style={"color": "red"})
            ])
            return (
                current_progress_data,
                True,
                error_container,
                {"display": "block", "marginTop": "15px"},
                error_status,
                False,
                completed_docs,
                progress_messages  # NEW: Return accumulated messages
            )
    
    raise dash.exceptions.PreventUpdate


# Pattern-matching callbacks for method and field generation with spinner
@app.callback(
    [Output({'type': 'method-doc-output', 'class': MATCH, 'method': MATCH}, 'children'),
     Output({'type': 'method-spinner', 'class': MATCH, 'method': MATCH}, 'style')],
    Input({'type': 'generate-method', 'class': MATCH, 'method': MATCH}, 'n_clicks'),
    Input('completed-docs-store', 'data'),
    State('parsed-store', 'data'),
    State('source-lines-store', 'data'),
    State({'type': 'method-doc-output', 'class': MATCH, 'method': MATCH}, 'id'),
    prevent_initial_call=True
)
def handle_method_documentation(n_clicks, completed_docs, parsed_data, source_lines, output_id):
    """
    Combined callback to handle both:
    1. Manual method generation (via Generate button click)
    2. Batch method generation (via completed-docs-store update)
    """
    triggered = callback_context.triggered
    if not triggered:
        raise dash.exceptions.PreventUpdate
    
    trigger_id = triggered[0]["prop_id"].split(".")[0]
    
    # Extract method info from output_id
    class_name = output_id.get('class')
    method_name = output_id.get('method')
    
    # TRIGGER 1: Manual button click
    if "generate-method" in trigger_id:
        if not n_clicks or not parsed_data:
            raise dash.exceptions.PreventUpdate
        
        try:
            generator = MethodDocGenerator(parsed_data, source_lines or [])
            methods = generator.list_methods()
            target = None
            for m in methods:
                if m.get('class_name') == class_name and m.get('method_name') == method_name:
                    target = m
                    break
            
            if not target:
                return html.Pre("Method not found in parsed data.", style={"color": "red"}), {"display": "none"}

            prompts = generator.build_prompts_for_method(target["class_index"], target["method_index"])
            docs = generator.run_all_prompts(prompts)
            
            # Convert docs to JSON
            docs_json = [doc.to_dict() if hasattr(doc, 'to_dict') else str(doc) for doc in docs]

            output = html.Div([
                html.H6("📤 LLM Output:", style={"marginTop": "12px", "color": "#17a2b8", "fontWeight": "bold"}),
                html.Pre(
                    json.dumps(docs_json, indent=2),
                    style={
                        "whiteSpace": "pre-wrap",
                        "backgroundColor": "#f0f8ff",
                        "padding": "12px",
                        "borderRadius": "4px",
                        "borderLeft": "3px solid #17a2b8",
                        "fontSize": "0.85em",
                        "maxHeight": "300px",
                        "overflowY": "auto"
                    }
                )
            ])
            
            return output, {"display": "none"}
            
        except Exception as e:
            return html.Pre(f"❌ Error: {str(e)}", style={"color": "red"}), {"display": "none"}
    
    # TRIGGER 2: Batch processing via completed-docs-store
    elif "completed-docs-store" in trigger_id:
        if not completed_docs:
            raise dash.exceptions.PreventUpdate
        
        doc_key = f"method_{class_name}_{method_name}"
        
        if doc_key not in completed_docs:
            raise dash.exceptions.PreventUpdate
        
        doc_data = completed_docs[doc_key]
        docs_json = doc_data.get("docs", [])
        
        output = html.Div([
            html.H6("📤 LLM Output (Batch):", style={"marginTop": "12px", "color": "#28a745", "fontWeight": "bold"}),
            html.Pre(
                json.dumps(docs_json, indent=2),
                style={
                    "whiteSpace": "pre-wrap",
                    "backgroundColor": "#f0fff4",
                    "padding": "12px",
                    "borderRadius": "4px",
                    "borderLeft": "3px solid #28a745",
                    "fontSize": "0.85em",
                    "maxHeight": "300px",
                    "overflowY": "auto"
                }
            )
        ])
        
        return output, {"display": "none"}
    
    raise dash.exceptions.PreventUpdate


@app.callback(
    [Output({'type': 'field-doc-output', 'class': MATCH, 'field': MATCH}, 'children'),
     Output({'type': 'field-spinner', 'class': MATCH, 'field': MATCH}, 'style')],
    Input({'type': 'generate-field', 'class': MATCH, 'field': MATCH}, 'n_clicks'),
    Input('completed-docs-store', 'data'),
    State('parsed-store', 'data'),
    State('source-lines-store', 'data'),
    State({'type': 'field-doc-output', 'class': MATCH, 'field': MATCH}, 'id'),
    prevent_initial_call=True
)
def handle_field_documentation(n_clicks, completed_docs, parsed_data, source_lines, output_id):
    """
    Combined callback to handle both:
    1. Manual field generation (via Generate button click)
    2. Batch field generation (via completed-docs-store update)
    """
    triggered = callback_context.triggered
    if not triggered:
        raise dash.exceptions.PreventUpdate
    
    trigger_id = triggered[0]["prop_id"].split(".")[0]
    
    # Extract field info from output_id
    class_name = output_id.get('class')
    field_name = output_id.get('field')
    
    # TRIGGER 1: Manual button click
    if "generate-field" in trigger_id:
        if not n_clicks or not parsed_data:
            raise dash.exceptions.PreventUpdate
        
        try:
            gen = FieldDocGenerator(parsed_data, source_lines or [])
            fields = gen.list_fields()
            target = None
            for f in fields:
                if f.get('class_name') == class_name and f.get('field_name') == field_name:
                    target = f
                    break
            
            if not target:
                return html.Pre("Field not found in parsed data.", style={"color": "red"}), {"display": "none"}

            # Build prompts and run all
            prompts = gen.build_prompts_for_field(target["class_index"], target["field_index"])
            docs = gen.run_all_prompts(prompts)
            
            # Convert docs to JSON
            docs_json = [doc.to_dict() if hasattr(doc, 'to_dict') else str(doc) for doc in docs]

            output = html.Div([
                html.H6("📤 LLM Output:", style={"marginTop": "12px", "color": "#17a2b8", "fontWeight": "bold"}),
                html.Pre(
                    json.dumps(docs_json, indent=2),
                    style={
                        "whiteSpace": "pre-wrap",
                        "backgroundColor": "#f0f8ff",
                        "padding": "12px",
                        "borderRadius": "4px",
                        "borderLeft": "3px solid #17a2b8",
                        "fontSize": "0.85em",
                        "maxHeight": "300px",
                        "overflowY": "auto"
                    }
                )
            ])
            
            return output, {"display": "none"}
            
        except Exception as e:
            return html.Pre(f"❌ Error: {str(e)}", style={"color": "red"}), {"display": "none"}
    
    # TRIGGER 2: Batch processing via completed-docs-store
    elif "completed-docs-store" in trigger_id:
        if not completed_docs:
            raise dash.exceptions.PreventUpdate
        
        doc_key = f"field_{class_name}_{field_name}"
        
        if doc_key not in completed_docs:
            raise dash.exceptions.PreventUpdate
        
        doc_data = completed_docs[doc_key]
        docs_json = doc_data.get("docs", [])
        
        output = html.Div([
            html.H6("📤 LLM Output (Batch):", style={"marginTop": "12px", "color": "#28a745", "fontWeight": "bold"}),
            html.Pre(
                json.dumps(docs_json, indent=2),
                style={
                    "whiteSpace": "pre-wrap",
                    "backgroundColor": "#f0fff4",
                    "padding": "12px",
                    "borderRadius": "4px",
                    "borderLeft": "3px solid #28a745",
                    "fontSize": "0.85em",
                    "maxHeight": "300px",
                    "overflowY": "auto"
                }
            )
        ])
        
        return output, {"display": "none"}
    
    raise dash.exceptions.PreventUpdate

if __name__ == "__main__":
    app.run(debug=True)
