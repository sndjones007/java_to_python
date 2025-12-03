# domain_doc_generator.py
import os
import json
import gc
from external_model_analyzer import ExternalModelAnalyzer
from llm_server import llm_chat
from env_config import EnvConfig

def load_prompt_template(filename: str) -> str:
    """Load a prompt template from the PROMPT_FOLDER."""
    path = os.path.join(EnvConfig.PROMPT_FOLDER, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

class DomainDoc:
    """
    Structured representation of documentation for a single external data model.
    """

    def __init__(self, model_name: str, description: str, usage_examples: list):
        self.model_name = model_name
        self.description = description
        self.usage_examples = usage_examples

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "description": self.description,
            "usage_examples": self.usage_examples,
        }

class DomainDocGenerator:
    def __init__(self, parser_results, source_code=""):
        self.analyzer = ExternalModelAnalyzer(parser_results, source_code)
        self.external_models_usages = self.analyzer.analyze()
        self.external_models = list(self.external_models_usages.keys())

    def build_prompt_for_model(self, model_name: str) -> str:
        usages = self.external_models_usages.get(model_name, [])
        template = load_prompt_template("domain_doc_prompt.txt")

        # Collect raw code lines as usage examples
        usage_examples = []
        for u in usages:
            for rc in u.get("raw_code", []):
                usage_examples.append(f"Line {rc['start_line']}: {rc['line']}")

        usage_examples_text = "\n".join(usage_examples) if usage_examples else "No usage examples available."

        # Fill template placeholders
        prompt = template.replace("{{MODEL_NAME}}", model_name)
        prompt = prompt.replace("{{USAGE_EXAMPLES}}", usage_examples_text)

        return prompt, usage_examples

    def run_prompt(self, model_name: str) -> DomainDoc:
        """
        Run the LLM prompt for a given external model and return a DomainDoc.
        Safer parsing of LLM output and attempts to free large temporary buffers
        as soon as possible to reduce peak memory usage.
        """

        prompt, usage_examples = self.build_prompt_for_model(model_name)

        messages = [
            {"role": "system", "content": "You are a helpful documentation assistant."},
            {"role": "user", "content": prompt},
        ]

        # Call the LLM
        output = llm_chat(messages)

        # Parse safely and free large temporaries quickly
        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            snippet = (output or "")[:1000]
            raise RuntimeError(f"LLM did not return valid JSON. Snippet: {snippet}") from e
        finally:
            # Attempt to free the raw LLM response immediately
            try:
                del output
            except Exception:
                pass
            gc.collect()

        # Build DomainDoc from parsed JSON, then release parsed JSON
        doc = DomainDoc(
            model_name=data.get("model_name", model_name),
            description=data.get("description", ""),
            usage_examples=usage_examples,
        )

        try:
            del data
        except Exception:
            pass
        gc.collect()

        return doc

    def run_all(self) -> list:
        docs = []
        for model in self.external_models:
            docs.append(self.run_prompt(model))
        return docs
