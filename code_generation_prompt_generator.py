"""
CodeGenerationPromptGenerator
- Takes LLM documentation output (MethodDoc or FieldDoc as JSON) and generates Python code
- Loads prompt template from python_generator_prompt.txt
- Fills placeholders: {{DOCUMENTATION_JSON_STRING}}
- Provides:
    - build_prompt(documentation_json_string) -> str
    - run_prompt(prompt) -> PythonCode
    - run_all_prompts(prompts) -> List[PythonCode]
"""
import os
import json
from typing import Dict, Any, Optional, List
from env_config import EnvConfig
from llm_server import llm_chat


# ----------------------------------------------------------------------
# Data Model for Generated Python Code
# ----------------------------------------------------------------------
class PythonCode:
    """
    Structured representation of generated Python code from Java.
    """

    def __init__(self, class_name: str, method_or_field_name: str, 
                 python_code: str, explanation: str):
        self.class_name = class_name
        self.method_or_field_name = method_or_field_name
        self.python_code = python_code
        self.explanation = explanation

    def to_dict(self) -> Dict[str, Any]:
        """Convert PythonCode object into a dictionary for serialization."""
        return {
            "class_name": self.class_name,
            "method_or_field_name": self.method_or_field_name,
            "python_code": self.python_code,
            "explanation": self.explanation,
        }


# ----------------------------------------------------------------------
# Prompt Loader
# ----------------------------------------------------------------------
def load_prompt_template(filename: str) -> str:
    """Load a prompt template from the PROMPT_FOLDER."""
    path = os.path.join(EnvConfig.PROMPT_FOLDER, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ----------------------------------------------------------------------
# CodeGenerationPromptGenerator class
# ----------------------------------------------------------------------
class CodeGenerationPromptGenerator:
    """Generates LLM prompts for converting Java code to Python using documentation JSON."""

    def __init__(self):
        """Initialize CodeGenerationPromptGenerator with the prompt template."""
        self._prompt_template = load_prompt_template("python_generator_prompt.txt")

    def build_prompt(self, documentation_json_string: str) -> str:
        """
        Build an LLM prompt to generate Python code from documentation JSON.
        
        Args:
            documentation_json_string: JSON string containing LLM documentation output
                                      (MethodDoc or FieldDoc as JSON string)
            
        Returns:
            Filled prompt string ready for LLM
            
        Raises:
            ValueError: If documentation_json_string is not valid JSON
        """
        # Validate that documentation_json_string is valid JSON
        try:
            json.loads(documentation_json_string)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON documentation string: {str(e)}")
        
        # Replace placeholder in template
        prompt = self._prompt_template.replace("{{DOCUMENTATION_JSON_STRING}}", documentation_json_string)
        
        return prompt

    def run_prompt(self, prompt: str) -> PythonCode:
        """
        Send a single prompt to the LLM and parse the JSON output into PythonCode.
        
        Args:
            prompt: The LLM prompt string
            
        Returns:
            PythonCode object with generated Python code
            
        Raises:
            RuntimeError: If LLM output is not valid JSON
        """
        messages = [
            {
                "role": "system", 
                "content": "You are an expert Python developer converting Java code to Python. Return valid JSON with keys: class_name, method_or_field_name, python_code, explanation."
            },
            {
                "role": "user", 
                "content": prompt
            },
        ]
        
        try:
            output = llm_chat(messages)
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {str(e)}")

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            raise RuntimeError(f"LLM did not return valid JSON. Output: {output[:200]}...")

        return PythonCode(
            class_name=data.get("class_name", ""),
            method_or_field_name=data.get("method_or_field_name", ""),
            python_code=data.get("python_code", ""),
            explanation=data.get("explanation", ""),
        )

    def run_all_prompts(self, prompts: List[str], on_progress: Optional[callable] = None) -> List[PythonCode]:
        """
        Run all prompts sequentially and return a list of PythonCode objects.
        
        Args:
            prompts: List of prompt strings
            on_progress: Optional callback function that receives status messages
            
        Returns:
            List of PythonCode objects (includes error objects on failure)
        """
        codes = []
        total = len(prompts)
        
        for idx, prompt in enumerate(prompts):
            try:
                if on_progress:
                    on_progress(f"Generating Python code {idx + 1}/{total}...")
                
                code = self.run_prompt(prompt)
                codes.append(code)
                
                if on_progress:
                    on_progress(f"✅ Python code {idx + 1}/{total} generated")
                    
            except Exception as e:
                if on_progress:
                    on_progress(f"❌ Error on code generation {idx + 1}: {str(e)}")
                
                # Create error code object
                error_code = PythonCode(
                    class_name="",
                    method_or_field_name="",
                    python_code=f"# ❌ Error: {str(e)}",
                    explanation=f"Code generation failed: {str(e)}"
                )
                codes.append(error_code)
        
        return codes
