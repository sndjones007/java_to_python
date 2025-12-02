"""
Unified LLM call utility.

Priority controlled by env flag:
- LLM_BACKEND=local → Local LLM (Ollama / TGI)
- LLM_BACKEND=azure → Azure OpenAI
"""

import requests
from env_config import EnvConfig  # centralized environment config
from openai import AzureOpenAI

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
    
    endpoint = EnvConfig.AZURE_OPENAI_ENDPOINT
    model_name = EnvConfig.AZURE_MODEL
    deployment = EnvConfig.AZURE_OPENAI_DEPLOYMENT

    subscription_key = EnvConfig.AZURE_OPENAI_API_KEY
    api_version = EnvConfig.AZURE_OPENAI_API_VERSION

    client = AzureOpenAI(
        api_version=api_version,
        azure_endpoint=endpoint,
        api_key=subscription_key,
    )

    try:
        response = client.chat.completions.create(
            messages=messages,
            max_tokens=EnvConfig.LLM_TOKEN_LIMIT,
            temperature=EnvConfig.LLM_TEMPERATURE,
            top_p=1.0,
            model=deployment
        )

        print("\n API is working! \n")
        output = response.choices[0].message.content
        output = output.strip("```json").strip("```").strip()
        return output

    except Exception as e:
        print("API call failed \n")
        print(e)
    
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
