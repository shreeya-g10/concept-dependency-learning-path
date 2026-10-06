"""The ONE place the project calls an LLM. Free providers only.

Every call is cached on disk (.cache/llm/) together with the model, temperature
and prompt version, so experiments are reproducible and re-runs cost nothing.

    from cdlp.shared.llm import chat, chat_json
    answer = chat("Is recursion a prerequisite of binary trees?", prompt_version="discover_v1")
    data = chat_json(prompt, system="Reply in JSON.", model=os.getenv("LLM_VALIDATOR_MODEL"))

Configure in .env (see .env.example). Default: Ollama on localhost.
"""

import hashlib
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "ollama")  # "ollama" | "openai_compatible"
BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434").rstrip("/")
DEFAULT_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")
API_KEY = os.getenv("LLM_API_KEY", "")
CACHE_DIR = Path(os.getenv("LLM_CACHE_DIR", ".cache/llm"))


def chat(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    temperature: float = 0.0,
    prompt_version: str = "unversioned",
    json_mode: bool = False,
) -> str:
    model = model or DEFAULT_MODEL
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    key = json.dumps([PROVIDER, model, temperature, json_mode, messages], sort_keys=True)
    cache_file = CACHE_DIR / f"{hashlib.sha256(key.encode()).hexdigest()}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())["response"]

    if PROVIDER == "ollama":
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            body["format"] = "json"
        resp = requests.post(f"{BASE_URL}/api/chat", json=body, timeout=600)
        resp.raise_for_status()
        text = resp.json()["message"]["content"]
    elif PROVIDER == "openai_compatible":
        body = {"model": model, "messages": messages, "temperature": temperature}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        resp = requests.post(
            f"{BASE_URL}/chat/completions",
            json=body,
            timeout=600,
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
    else:
        raise ValueError(f"Unknown LLM_PROVIDER {PROVIDER!r}")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "provider": PROVIDER,
                "model": model,
                "temperature": temperature,
                "prompt_version": prompt_version,
                "messages": messages,
                "response": text,
                "created": time.time(),
            },
            indent=2,
        )
    )
    return text


def chat_json(prompt: str, **kwargs) -> dict:
    return json.loads(chat(prompt, json_mode=True, **kwargs))
