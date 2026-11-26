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


def test_health_without_key_and_provider_switch(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("FORGE_EMBED_VIA_OLLAMA", raising=False)
    assert GroqLLM().health() == {"ok": False, "error": "GROQ_API_KEY is not set", "provider": "groq"}
    monkeypatch.setenv("FORGE_PROVIDER", "groq")
    assert isinstance(make_llm(), GroqLLM)
    assert isinstance(make_llm("ollama"), OllamaLLM)
    assert GroqLLM().embed_model is None  # BM25 unless embeddings are routed to Ollama
