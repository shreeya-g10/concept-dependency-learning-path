"""The LLM client sends the seed to the provider and keys the cache on it. No network."""

import json

import pytest

from cdlp.shared import llm


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


@pytest.fixture
def sent(monkeypatch, tmp_path):
    """Captures every request body; answers like the configured provider would."""
    bodies = []

    def fake_post(url, json=None, **kwargs):
        bodies.append(json)
        if llm.PROVIDER == "ollama":
            return FakeResponse({"message": {"content": "ok"}})
        return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    return bodies


@pytest.mark.parametrize("provider", ["ollama", "openai_compatible"])
def test_seed_is_sent_to_the_provider(sent, monkeypatch, provider):
    monkeypatch.setattr(llm, "PROVIDER", provider)

    llm.chat("hi", seed=7)

    body = sent[0]
    assert (body["options"]["seed"] if provider == "ollama" else body["seed"]) == 7


def test_default_seed_is_42(sent, monkeypatch):
    monkeypatch.setattr(llm, "PROVIDER", "ollama")

    llm.chat("hi")

    assert sent[0]["options"]["seed"] == llm.DEFAULT_SEED == 42


def test_seed_is_in_cache_key_and_record(sent, monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "PROVIDER", "ollama")

    llm.chat("hi", seed=1)
    llm.chat("hi", seed=1)  # cached
    llm.chat("hi", seed=2)  # different key -> new request

    assert [body["options"]["seed"] for body in sent] == [1, 2]
    records = [json.loads(p.read_text()) for p in tmp_path.glob("*.json")]
    assert sorted(r["seed"] for r in records) == [1, 2]
