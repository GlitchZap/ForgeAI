"""GroqLLM against a fake HTTP transport: rate-limit retry, JSON mode, schema retry, key never traced."""
import json

import httpx

from forgeai.llm import GroqLLM, OllamaLLM, make_llm
from forgeai.schemas import JudgeOut


def _client(handler):
    llm = GroqLLM(api_key="test-key-not-real", model="llama-3.1-8b-instant", judge_model="qwen/qwen3-32b")
    llm.http = httpx.Client(transport=httpx.MockTransport(handler))
    return llm


def test_retries_rate_limit_then_parses_json(tmp_path, monkeypatch):
    monkeypatch.setattr("forgeai.llm.time.sleep", lambda s: None)
    calls = []

    def handler(req):
        body = json.loads(req.content)
        calls.append(body)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "1"}, json={"error": "slow down"})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"facts_present":[true],"unsupported_claims":[]}'}}],
                                         "usage": {"total_tokens": 42}})
    llm = _client(handler)
    llm.trace_path = tmp_path / "trace.jsonl"
    out = llm.structured([{"role": "user", "content": "grade this"}], JudgeOut, judge=True)
    assert out.facts_present == [True] and len(calls) == 2
    assert calls[1]["model"] == "qwen/qwen3-32b" and calls[1]["response_format"] == {"type": "json_object"}
    assert "JSON schema" in calls[1]["messages"][-1]["content"] and calls[1].get("reasoning_effort") == "none"
    assert llm.tokens_used == 42
    assert "test-key-not-real" not in (tmp_path / "trace.jsonl").read_text()


def test_daily_limit_switches_model_without_waiting(monkeypatch):
    monkeypatch.setattr("forgeai.llm._groq_spent", {})
    monkeypatch.setattr("forgeai.llm.time.sleep", lambda s: (_ for _ in ()).throw(AssertionError("must not wait")))
    models = []

    def handler(req):
        models.append(json.loads(req.content)["model"])
        if models[-1] == "openai/gpt-oss-20b":  # tokens-per-day spent: Groq says wait ~27 min
            return httpx.Response(429, headers={"retry-after": "1637"}, json={"error": "TPD"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "24 days"}}], "usage": {"total_tokens": 5}})
    llm = GroqLLM(api_key="test-key-not-real")
    llm.http = httpx.Client(transport=httpx.MockTransport(handler))
    assert llm.chat([{"role": "user", "content": "leave?"}]) == "24 days"
    assert llm.chat([{"role": "user", "content": "again"}]) == "24 days"
    assert models == ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "openai/gpt-oss-120b"]  # spent model skipped next time


def test_health_without_key_and_provider_switch(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("FORGE_EMBED_VIA_OLLAMA", raising=False)
    assert GroqLLM().health() == {"ok": False, "error": "GROQ_API_KEY is not set", "provider": "groq"}
    monkeypatch.setenv("FORGE_PROVIDER", "groq")
    assert isinstance(make_llm(), GroqLLM)
    assert isinstance(make_llm("ollama"), OllamaLLM)
    assert GroqLLM().embed_model is None  # BM25 unless embeddings are routed to Ollama


def test_groq_takes_over_when_ollama_is_down(monkeypatch):
    monkeypatch.setattr("forgeai.llm.ollama_up", lambda: False)
    monkeypatch.setenv("FORGE_EMBED_VIA_OLLAMA", "1")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    llm = make_llm("ollama", model="qwen2.5:7b", judge_model="llama3.1:8b", embed_model="nomic-embed-text")
    assert isinstance(llm, GroqLLM)
    assert (llm.model, llm.judge_model, llm.embed_model) == (GroqLLM.MODEL, GroqLLM.JUDGE, None)  # no Ollama tags, BM25 only
    monkeypatch.delenv("GROQ_API_KEY")
    assert isinstance(make_llm("ollama"), OllamaLLM)  # no key: nothing to fall back to, health reports Ollama down
