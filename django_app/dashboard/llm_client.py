import os

import requests


LLM_API_STYLE = os.environ.get("AUDIT_LLM_API_STYLE", "ollama").lower()
LLM_BASE_URL = os.environ.get(
    "AUDIT_LLM_BASE_URL",
    os.environ.get("OLLAMA_URL", "http://localhost:11434"),
).rstrip("/")
LLM_MODEL = os.environ.get("AUDIT_OLLAMA_MODEL", "deepseek-r1:1.5b")
LLM_API_KEY = os.environ.get("AUDIT_LLM_API_KEY", "")


def is_available(timeout=2.5):
    endpoint = "/models" if LLM_API_STYLE == "openai-compatible" else "/api/tags"
    try:
        response = requests.get(f"{LLM_BASE_URL}{endpoint}", timeout=timeout)
        return response.status_code == 200
    except requests.RequestException:
        return False


def generate(prompt, *, timeout=25, temperature=0.2, max_tokens=900):
    if LLM_API_STYLE == "openai-compatible":
        headers = {"Content-Type": "application/json"}
        if LLM_API_KEY:
            headers["Authorization"] = f"Bearer {LLM_API_KEY}"
        response = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=headers,
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        choices = response.json().get("choices") or []
        if not choices:
            raise ValueError("LLM response did not contain a completion")
        return choices[0].get("message", {}).get("content", "")

    response = requests.post(
        f"{LLM_BASE_URL}/api/generate",
        json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json().get("response", "")
