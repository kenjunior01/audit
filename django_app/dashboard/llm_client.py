"""Cliente LLM multi-provider da plataforma AuditAI Omni.

Providers (ordem de prioridade da cadeia, `auto` por omissão):
1. nvidia  — NVIDIA NIM (OpenAI-compatible, integrate.api.nvidia.com), ativo
             quando AUDIT_NVIDIA_API_KEY (ou NVIDIA_API_KEY) definida. Suporta
             reasoning do Nemotron (AUDIT_LLM_REASONING=true →
             chat_template_kwargs.enable_thinking); o raciocínio
             (reasoning_content) é descartado — só a resposta final regressa.
2. primary — provider clássico configurado com AUDIT_LLM_API_STYLE:
             'openai-compatible' (Groq/EXAONE/vLLM/qualquer API estilo OpenAI)
             ou 'ollama' (local, AUDIT_LLM_BASE_URL/OLLAMA_URL).

`generate()` mantém a assinatura histórica (devolve texto) mas agora percorre
a cadeia nvidia → primary, caindo para o provider seguinte em caso de falha
(rede, auth, modelo indisponível). Acrescentados: `generate_meta()` (texto +
provider/modelo/latência), `generate_stream()` (gerador de chunks para SSE)
e `provider_status()` (estado dos motores para o painel de Integrações).
"""
import json
import os
import re
import time

import requests

# ---------------------------------------------------------------------------
# Provider 1 — NVIDIA NIM (Nemotron e catálogo NVIDIA)
# ---------------------------------------------------------------------------
NVIDIA_API_KEY = (os.environ.get("AUDIT_NVIDIA_API_KEY")
                  or os.environ.get("NVIDIA_API_KEY", ""))
NVIDIA_BASE_URL = os.environ.get(
    "AUDIT_NVIDIA_BASE_URL",
    "https://integrate.api.nvidia.com/v1").rstrip("/")
NVIDIA_MODEL = os.environ.get(
    "AUDIT_NVIDIA_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
NVIDIA_REASONING = os.environ.get("AUDIT_LLM_REASONING", "False").lower() in (
    "1", "true", "yes", "on")

# ---------------------------------------------------------------------------
# Provider 2 — primário clássico (ollama / openai-compatible) — constantes
# históricas mantidas para retro-compatibilidade (testes fazem patch delas)
# ---------------------------------------------------------------------------
LLM_API_STYLE = os.environ.get("AUDIT_LLM_API_STYLE", "ollama").lower()
LLM_BASE_URL = os.environ.get(
    "AUDIT_LLM_BASE_URL",
    os.environ.get("OLLAMA_URL", "http://localhost:11434"),
).rstrip("/")
LLM_MODEL = os.environ.get("AUDIT_OLLAMA_MODEL", "deepseek-r1:1.5b")
LLM_API_KEY = os.environ.get("AUDIT_LLM_API_KEY") or os.environ.get("GROQ_API_KEY", "")

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def _text_cfg():
    """Config efetiva do slot text: BD (credencial encriptada) → env →
    constantes de módulo (retro-compatibilidade com testes/install via env).
    Nunca lança; devolve {'api_key','model','base_url','source'}."""
    try:
        from . import ai_credentials
        cfg = ai_credentials.resolve_slot("text")
        if cfg.get("api_key"):
            return cfg
    except Exception:
        pass
    return {"api_key": NVIDIA_API_KEY, "model": NVIDIA_MODEL,
            "base_url": NVIDIA_BASE_URL,
            "source": "module" if NVIDIA_API_KEY else ""}


def openai_compatible_headers():
    headers = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"
    return headers


def _clean_content(text):
    """Remove blocos de raciocínio inline (<think>…</think>) e espaços extra."""
    if not text:
        return ""
    return _THINK_RE.sub("", text).strip()


def _openai_headers(api_key):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


# ---------------------------------------------------------------------------
# Probes de disponibilidade
# ---------------------------------------------------------------------------
def _nvidia_probe(timeout=2.5):
    cfg = _text_cfg()
    if not cfg["api_key"]:
        return False
    try:
        response = requests.get(
            f"{cfg['base_url']}/models",
            headers={"Authorization": f"Bearer {cfg['api_key']}"},
            timeout=timeout)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _primary_probe(timeout=2.5):
    if "api.groq.com" in LLM_BASE_URL and not LLM_API_KEY:
        return False
    endpoint = "/models" if LLM_API_STYLE == "openai-compatible" else "/api/tags"
    try:
        kwargs = {"timeout": timeout}
        if LLM_API_STYLE == "openai-compatible":
            kwargs["headers"] = openai_compatible_headers()
        response = requests.get(f"{LLM_BASE_URL}{endpoint}", **kwargs)
        return response.status_code == 200
    except requests.RequestException:
        return False


def is_available(timeout=2.5):
    """True se qualquer motor da cadeia responde."""
    return _nvidia_probe(timeout) or _primary_probe(timeout)


# ---------------------------------------------------------------------------
# Geração (não-streaming) por provider
# ---------------------------------------------------------------------------
def _nvidia_generate(prompt, *, timeout, temperature, max_tokens):
    cfg = _text_cfg()
    body = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if NVIDIA_REASONING:
        body["chat_template_kwargs"] = {"enable_thinking": True}
    response = requests.post(
        f"{cfg['base_url']}/chat/completions",
        headers=_openai_headers(cfg["api_key"]),
        json=body,
        timeout=timeout,
    )
    response.raise_for_status()
    choices = response.json().get("choices") or []
    if not choices:
        raise ValueError("NVIDIA NIM response did not contain a completion")
    message = choices[0].get("message") or {}
    return _clean_content(message.get("content") or "")


def _primary_generate(prompt, *, timeout, temperature, max_tokens):
    if LLM_API_STYLE == "openai-compatible":
        response = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=_openai_headers(LLM_API_KEY),
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
        return _clean_content(choices[0].get("message", {}).get("content", ""))

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
    return _clean_content(response.json().get("response", ""))


# ---------------------------------------------------------------------------
# Cadeia: nvidia → primary (com metadados)
# ---------------------------------------------------------------------------
def generate_meta(prompt, *, timeout=25, temperature=0.2, max_tokens=900):
    """Devolve (texto, meta{provider, model, latency_ms}). Percorre a cadeia."""
    providers = (["nvidia"] if _text_cfg()["api_key"] else []) + ["primary"]
    last_error = None
    for pid in providers:
        start = time.monotonic()
        try:
            if pid == "nvidia":
                text = _nvidia_generate(prompt, timeout=timeout,
                                        temperature=temperature,
                                        max_tokens=max_tokens)
                model = _text_cfg()["model"]
            else:
                text = _primary_generate(prompt, timeout=timeout,
                                         temperature=temperature,
                                         max_tokens=max_tokens)
                model = LLM_MODEL
            return text, {"provider": pid, "model": model,
                          "latency_ms": int((time.monotonic() - start) * 1000)}
        except (requests.RequestException, ValueError) as e:
            last_error = e
    raise last_error if last_error else RuntimeError("Nenhum provider LLM configurado")


def generate(prompt, *, timeout=25, temperature=0.2, max_tokens=900,
             provider="auto"):
    """Geração simples (texto). provider='nvidia'|'primary' força um motor."""
    if provider == "nvidia":
        return _nvidia_generate(prompt, timeout=timeout, temperature=temperature,
                                max_tokens=max_tokens)
    if provider in ("primary", "ollama", "openai-compatible"):
        return _primary_generate(prompt, timeout=timeout, temperature=temperature,
                                 max_tokens=max_tokens)
    text, _meta = generate_meta(prompt, timeout=timeout, temperature=temperature,
                                max_tokens=max_tokens)
    return text


# ---------------------------------------------------------------------------
# Streaming (chunks de texto; reasoning_content descartado)
# ---------------------------------------------------------------------------
def _iter_openai_sse(response):
    for raw in response.iter_lines():
        if not raw:
            continue
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            return
        try:
            chunk = json.loads(payload)
        except ValueError:
            continue
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        # reasoning_content (Nemotron thinking) é descartado de propósito
        content = delta.get("content")
        if content:
            yield content


def _nvidia_generate_stream(prompt, *, timeout, temperature, max_tokens):
    cfg = _text_cfg()
    body = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if NVIDIA_REASONING:
        body["chat_template_kwargs"] = {"enable_thinking": True}
    response = requests.post(
        f"{cfg['base_url']}/chat/completions",
        headers=_openai_headers(cfg["api_key"]),
        json=body, timeout=timeout, stream=True)
    response.raise_for_status()
    yield from _iter_openai_sse(response)


def _primary_generate_stream(prompt, *, timeout, temperature, max_tokens):
    if LLM_API_STYLE == "openai-compatible":
        response = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=_openai_headers(LLM_API_KEY),
            json={"model": LLM_MODEL,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": temperature, "max_tokens": max_tokens,
                  "stream": True},
            timeout=timeout, stream=True)
        response.raise_for_status()
        yield from _iter_openai_sse(response)
        return
    response = requests.post(
        f"{LLM_BASE_URL}/api/generate",
        json={"model": LLM_MODEL, "prompt": prompt, "stream": True,
              "options": {"temperature": temperature, "num_predict": max_tokens}},
        timeout=timeout, stream=True)
    response.raise_for_status()
    for raw in response.iter_lines():
        if not raw:
            continue
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        try:
            chunk = json.loads(line)
        except ValueError:
            continue
        if chunk.get("done"):
            return
        if chunk.get("response"):
            yield chunk["response"]


def generate_stream(prompt, *, timeout=60, temperature=0.2, max_tokens=900,
                    provider=None):
    """Gerador de chunks de texto: tenta nvidia → primary (SSE)."""
    if _text_cfg()["api_key"] and provider in (None, "nvidia"):
        try:
            yield from _nvidia_generate_stream(prompt, timeout=timeout,
                                               temperature=temperature,
                                               max_tokens=max_tokens)
            return
        except requests.RequestException:
            if provider == "nvidia":
                raise
    yield from _primary_generate_stream(prompt, timeout=timeout,
                                        temperature=temperature,
                                        max_tokens=max_tokens)


# ---------------------------------------------------------------------------
# Estado dos motores (para o painel de Integrações)
# ---------------------------------------------------------------------------
def provider_status(timeout=2.5):
    """Lista os motores configurados com disponibilidade ao vivo."""
    cfg = _text_cfg()
    out = [{
        "id": "nvidia", "priority": 1,
        "label": "NVIDIA NIM", "style": "openai-compatible",
        "base_url": cfg["base_url"], "model": cfg["model"],
        "auth": bool(cfg["api_key"]), "reasoning": NVIDIA_REASONING,
        "configured": bool(cfg["api_key"]),
        "source": cfg["source"],
        "available": _nvidia_probe(timeout),
    }, {
        "id": "primary", "priority": 2,
        "label": ("Ollama local" if LLM_API_STYLE == "ollama"
                  else "OpenAI-compatible"),
        "style": LLM_API_STYLE, "base_url": LLM_BASE_URL, "model": LLM_MODEL,
        "auth": bool(LLM_API_KEY), "reasoning": False,
        "configured": True,
        "available": _primary_probe(timeout),
    }]
    return out
