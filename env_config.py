"""
Centralized environment configuration loader.
All agents and utilities import from here instead of calling os.getenv directly.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class EnvConfig:
    # Prompt folder and backend
    PROMPT_FOLDER: str = os.getenv("PROMPT_FOLDER", "prompts")
    LLM_BACKEND: str = os.getenv("LLM_BACKEND", "local").lower()  # "local" or "azure"

    # Local LLM
    LOCAL_LLM_URL: str = os.getenv("LOCAL_LLM_URL")
    LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL")
    LOCAL_LLM_TIMEOUT: int = int(os.getenv("LOCAL_LLM_TIMEOUT", "60"))

    # Temperature
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))

    # Azure OpenAI
    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT")
    AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY")
    AZURE_OPENAI_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    AZURE_OPENAI_API_VERSION: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

    # OpenAI fallback
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")

    # Output folders
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "output")
    UNIFIED_DIR: str = os.getenv("UNIFIED_DIR", "unified_specs")
    SUMMARIES_DIR: str = os.getenv("SUMMARIES_DIR", "summaries")

    # Streamlit
    STREAMLIT_PORT: int = int(os.getenv("STREAMLIT_PORT", "8501"))

    # Testing paths
    TEST_JAVA_FILE_LOC: str = os.getenv("TEST_JAVA_FILE_LOC", "testdata/java")
    TEST_JAVA_TO_PYTHON_FILE_LOC: str = os.getenv("TEST_JAVA_TO_PYTHON_FILE_LOC", "testdata/python")
    # Token limit
    LLM_TOKEN_LIMIT: int = int(os.getenv("LLM_TOKEN_LIMIT", "2000"))