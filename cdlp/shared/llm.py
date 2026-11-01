"""The ONE place the project calls an LLM. Free providers only.

Every call is cached on disk (.cache/llm/) together with the model, temperature
and prompt version, so experiments are reproducible and re-runs cost nothing.

    from cdlp.shared.llm import chat, chat_json
    answer = chat("Is recursion a prerequisite of binary trees?", prompt_version="discover_v1")
    data = chat_json(prompt, system="Reply in JSON.", model=os.getenv("LLM_VALIDATOR_MODEL"))

Configure in .env (see .env.example). Default: Ollama on localhost.

Per-process call counts, for the cost columns of the experiments:

    from cdlp.shared.llm import write_stats
    write_stats("outputs/rq1/ds101/full_agent.stats.json")
    # {"llm_calls": 12, "cache_hits": 30, "model": "llama3.1:8b", "prompt_versions": [...]}
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
# Sent as options.seed (Ollama) / seed (OpenAI-compatible) and part of the cache key.
DEFAULT_SEED = 42

# Counted per process: real provider calls, cache hits, models and prompt versions used.
_STATS: dict = {"llm_calls": 0, "cache_hits": 0, "models": set(), "prompt_versions": set()}


def chat(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    temperature: float = 0.0,
    prompt_version: str = "unversioned",
    json_mode: bool = False,
    seed: int = DEFAULT_SEED,
) -> str:
    model = model or DEFAULT_MODEL
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    key = json.dumps([PROVIDER, model, temperature, seed, json_mode, messages], sort_keys=True)
    cache_file = CACHE_DIR / f"{hashlib.sha256(key.encode()).hexdigest()}.json"
    if cache_file.exists():
        response = json.loads(cache_file.read_text())["response"]
        _record("cache_hits", model, prompt_version)
        return response

    if PROVIDER == "ollama":
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "seed": seed},
        }
        if json_mode:
            body["format"] = "json"
        resp = requests.post(f"{BASE_URL}/api/chat", json=body, timeout=600)
        resp.raise_for_status()
        text = resp.json()["message"]["content"]
    elif PROVIDER == "openai_compatible":
        body = {"model": model, "messages": messages, "temperature": temperature, "seed": seed}
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
    _record("llm_calls", model, prompt_version)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "provider": PROVIDER,
                "model": model,
                "temperature": temperature,
                "seed": seed,
                "prompt_version": prompt_version,
                "messages": messages,
                "response": text,
                "created": time.time(),
            },
            indent=2,
        )
    )
    return text


def _record(counter: str, model: str, prompt_version: str) -> None:
    _STATS[counter] += 1
    _STATS["models"].add(model)
    _STATS["prompt_versions"].add(prompt_version)


def get_stats() -> dict:
    """Counts since the process started (or the last reset_stats()).

    llm_calls: requests the provider answered. cache_hits: answers read from .cache/llm/.
    model: the one model used, a sorted list if several were used, None if none.
    """
    models = sorted(_STATS["models"])
    return {
        "llm_calls": _STATS["llm_calls"],
        "cache_hits": _STATS["cache_hits"],
        "model": models[0] if len(models) == 1 else (models or None),
        "prompt_versions": sorted(_STATS["prompt_versions"]),
    }


def reset_stats() -> None:
    _STATS.update(llm_calls=0, cache_hits=0, models=set(), prompt_versions=set())


def write_stats(path: Path | str) -> dict:
    """Write get_stats() as JSON to path (parent folders created) and return it."""
    stats = get_stats()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stats, indent=2) + "\n")
    return stats


def chat_json(prompt: str, **kwargs) -> dict:
    return json.loads(chat(prompt, json_mode=True, **kwargs))
