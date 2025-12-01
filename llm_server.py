"""
Unified LLM call utility.

Priority controlled by env flag:
- LLM_BACKEND=local → Local LLM (Ollama / TGI)
- LLM_BACKEND=azure → Azure OpenAI
"""

import requests
from env_config import EnvConfig  # centralized environment config


# -----------------------------------------------------
# Internal helper: Local LLM
# -----------------------------------------------------
def _call_local_llm(messages, model=None):
    if not EnvConfig.LOCAL_LLM_URL:
        raise RuntimeError("LOCAL_LLM_URL not configured")

    url = EnvConfig.LOCAL_LLM_URL.rstrip("/") + "/v1/chat/completions"

    payload = {
        "model": model or EnvConfig.LOCAL_LLM_MODEL,
        "temperature": EnvConfig.LLM_TEMPERATURE,
        "messages": messages,
    }

    response = requests.post(url, json=payload, timeout=EnvConfig.LOCAL_LLM_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


# -----------------------------------------------------
# Internal helper: Azure OpenAI
# -----------------------------------------------------
def _call_azure_llm(messages):
    if not EnvConfig.AZURE_OPENAI_API_KEY:
        raise RuntimeError("Azure OpenAI API Key missing.")

    url = (
        f"{EnvConfig.AZURE_OPENAI_ENDPOINT}/openai/deployments/"
        f"{EnvConfig.AZURE_OPENAI_DEPLOYMENT}/chat/completions"
        f"?api-version={EnvConfig.AZURE_OPENAI_API_VERSION}"
    )

    headers = {
        "Content-Type": "application/json",
        "api-key": EnvConfig.AZURE_OPENAI_API_KEY,
    }

    payload = {
        "messages": messages,
        "temperature": EnvConfig.LLM_TEMPERATURE,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=EnvConfig.LOCAL_LLM_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


# -----------------------------------------------------
# Public API
# -----------------------------------------------------
def llm_chat(messages, model=None):
    """
    Main unified LLM caller.
    Chooses backend based on EnvConfig.LLM_BACKEND flag.
    """
    if EnvConfig.LLM_BACKEND == "local":
        return _call_local_llm(messages, model)

    if EnvConfig.LLM_BACKEND == "azure":
        return _call_azure_llm(messages)

    raise RuntimeError("Invalid LLM_BACKEND. Use 'local' or 'azure'.")
