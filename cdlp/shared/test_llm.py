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


# ---- per-process call stats ---------------------------------------------------
@pytest.fixture
def fresh_stats():
    llm.reset_stats()
    yield
    llm.reset_stats()


def test_stats_count_real_calls_and_cache_hits(sent, monkeypatch, fresh_stats):
    monkeypatch.setattr(llm, "PROVIDER", "ollama")

    llm.chat("a", model="m1", prompt_version="p_v1")
    llm.chat("a", model="m1", prompt_version="p_v1")  # cache hit
    llm.chat("b", model="m1", prompt_version="q_v2")

    assert len(sent) == 2
    assert llm.get_stats() == {
        "llm_calls": 2,
        "cache_hits": 1,
        "model": "m1",
        "prompt_versions": ["p_v1", "q_v2"],
    }


def test_stats_list_every_model_when_several_are_used(sent, monkeypatch, fresh_stats):
    monkeypatch.setattr(llm, "PROVIDER", "ollama")
    assert llm.get_stats()["model"] is None

    llm.chat("a", model="m2")
    llm.chat("a", model="m1")

    assert llm.get_stats()["model"] == ["m1", "m2"]


def test_failed_request_is_not_counted(monkeypatch, tmp_path, fresh_stats):
    def boom(*args, **kwargs):
        raise llm.requests.ConnectionError("unreachable")

    monkeypatch.setattr(llm.requests, "post", boom)
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    with pytest.raises(llm.requests.ConnectionError):
        llm.chat("hi")

    assert llm.get_stats()["llm_calls"] == 0


def test_cache_key_is_unchanged_by_stats(sent, monkeypatch, tmp_path, fresh_stats):
    """Responses cached before the counters existed are still found."""
    import hashlib

    monkeypatch.setattr(llm, "PROVIDER", "ollama")
    messages = [{"role": "user", "content": "hi"}]
    key = json.dumps(["ollama", "m", 0.0, 42, False, messages], sort_keys=True)
    (tmp_path / f"{hashlib.sha256(key.encode()).hexdigest()}.json").write_text(
        json.dumps({"response": "from cache"})
    )

    assert llm.chat("hi", model="m") == "from cache"
    assert sent == []
    assert llm.get_stats()["cache_hits"] == 1


def test_write_stats(sent, monkeypatch, tmp_path, fresh_stats):
    monkeypatch.setattr(llm, "PROVIDER", "ollama")
    llm.chat("a", model="m1", prompt_version="p_v1")

    out = tmp_path / "run" / "full_agent.stats.json"
    returned = llm.write_stats(out)

    assert (
        json.loads(out.read_text())
        == returned
        == {
            "llm_calls": 1,
            "cache_hits": 0,
            "model": "m1",
            "prompt_versions": ["p_v1"],
        }
    )
