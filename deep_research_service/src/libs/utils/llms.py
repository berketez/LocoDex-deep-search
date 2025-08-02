import os
import requests
from typing import Any, Optional

import tenacity
from litellm import acompletion, completion

# Determine the active LLM provider
OLLAMA_HOST = os.environ.get("OLLAMA_HOST")
LMSTUDIO_HOST = os.environ.get("LMSTUDIO_HOST")

API_BASE = None
PROVIDER = None

if OLLAMA_HOST:
    try:
        requests.get(OLLAMA_HOST, timeout=2)
        API_BASE = OLLAMA_HOST
        PROVIDER = "ollama"
    except requests.exceptions.RequestException:
        pass

if not API_BASE and LMSTUDIO_HOST:
    try:
        requests.get(LMSTUDIO_HOST, timeout=2)
        API_BASE = LMSTUDIO_HOST
        PROVIDER = "lmstudio"
    except requests.exceptions.RequestException:
        pass

if not API_BASE:
    # Default to Ollama if neither is available, but log a warning
    print("Warning: Neither Ollama nor LM Studio is available. Defaulting to Ollama.")
    API_BASE = "http://localhost:11434"
    PROVIDER = "ollama"

@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_exponential(multiplier=1, min=4, max=15))
async def asingle_shot_llm_call(
    model: str,
    system_prompt: str,
    message: str,
    response_format: Optional[dict[str, str | dict[str, Any]]] = None,
    max_completion_tokens: int | None = None,
) -> str:
    model_string = f"{PROVIDER}/{model}" if PROVIDER else model
    response = await acompletion(
        model=model_string,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": message}],
        temperature=0.0,
        response_format=response_format,
        max_tokens=max_completion_tokens,
        api_base=API_BASE,
        timeout=600,
    )
    return response.choices[0].message.content  # type: ignore


@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_exponential(multiplier=1, min=4, max=15))
def single_shot_llm_call(
    model: str,
    system_prompt: str,
    message: str,
    response_format: Optional[dict[str, str | dict[str, Any]]] = None,
    max_completion_tokens: int | None = None,
) -> str:
    model_string = f"{PROVIDER}/{model}" if PROVIDER else model
    response = completion(
        model=model_string,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": message}],
        temperature=0.0,
        response_format=response_format,
        max_tokens=max_completion_tokens,
        api_base=API_BASE,
        timeout=600,
    )
    return response.choices[0].message.content  # type: ignore


def generate_toc_image(prompt: str, planning_model: str, topic: str) -> str:
    """Generate a table of contents image - NOT IMPLEMENTED FOR LOCAL MODELS"""
    # This function is not supported for local models in this integration.
    # Returning an empty string as a placeholder.
    return ""


