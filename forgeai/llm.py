"""LLM access layer. Every call is traced, budgeted, and (for structured calls) schema-validated with retries.

Small local models break JSON and drift off-schema, so `structured()` sends the Pydantic JSON schema to
Ollama's `format` field AND re-validates locally, feeding the validation error back on retry.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class BudgetExceeded(RuntimeError):
    pass


class LLMError(RuntimeError):
    pass


class LLM:
    """Base client. Subclasses implement `_chat_raw` and `_embed_raw`."""

    def __init__(self, model: str, judge_model: str | None = None, embed_model: str | None = None,
                 trace_path: Path | None = None, token_budget: int | None = None, seed: int = 42):
        self.model = model
        self.judge_model = judge_model or model
        self.embed_model = embed_model
        self.trace_path = trace_path
        self.token_budget = token_budget
        self.seed = seed
        self.tokens_used = 0
        self.calls = 0
        self.stage = "init"
        self.on_call = None  # optional heartbeat: callable(phase, info) around every model call

    # --- subclass hooks -------------------------------------------------
    def _chat_raw(self, messages: list[dict], model: str, schema: dict | None, temperature: float) -> tuple[str, int]:
        raise NotImplementedError

    def _embed_raw(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    # --- public API -----------------------------------------------------
    def chat(self, messages: list[dict], *, schema: dict | None = None, temperature: float = 0.0,
             judge: bool = False) -> str:
        if self.token_budget is not None and self.tokens_used >= self.token_budget:
            raise BudgetExceeded(f"token budget {self.token_budget} exhausted")
        model = self.judge_model if judge else self.model
        t0 = time.perf_counter()
        if self.on_call:
            self.on_call("start", {"llm_stage": self.stage, "model": model})
        text, tokens = self._chat_raw(messages, model, schema, temperature)
        self.tokens_used += tokens
        self.calls += 1
        if self.on_call:
            self.on_call("done", {"llm_stage": self.stage, "model": model, "tokens": tokens,
                                  "latency_s": round(time.perf_counter() - t0, 2)})
        self._trace({"stage": self.stage, "model": model, "messages": messages, "output": text,
                     "tokens": tokens, "latency_s": round(time.perf_counter() - t0, 3)})
        return text

    def structured(self, messages: list[dict], model_cls: type[T], *, temperature: float = 0.0,
                   judge: bool = False, retries: int = 2) -> T:
        schema = model_cls.model_json_schema()
        msgs = list(messages)
        last_err = ""
        for _ in range(retries + 1):
            text = self.chat(msgs, schema=schema, temperature=temperature, judge=judge)
            try:
                return model_cls.model_validate_json(_extract_json(text))
            except (ValidationError, ValueError) as e:
                last_err = str(e)[:800]
                msgs = msgs + [{"role": "assistant", "content": text},
                               {"role": "user", "content": f"That JSON was invalid: {last_err}\nReturn ONLY corrected JSON matching the schema."}]
        raise LLMError(f"{model_cls.__name__}: no valid output after {retries + 1} tries: {last_err}")

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.embed_model:
            raise LLMError("no embedding model configured")
        cache = self.__dict__.setdefault("_emb_cache", {})  # re-indexing after a chunking change reuses vectors
        todo = [t for t in dict.fromkeys(texts) if t not in cache]
        if todo:
            cache.update(zip(todo, self._embed_raw(todo)))
        return [cache[t] for t in texts]

    def _trace(self, rec: dict) -> None:
        if self.trace_path:
            rec["ts"] = time.time()
            with open(self.trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _extract_json(text: str) -> str:
    """Tolerate ```json fences and leading chatter from small models."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("\n") + 1:] if "\n" in t else t
    start = min([i for i in (t.find("{"), t.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON object in output")
    end = max(t.rfind("}"), t.rfind("]"))
    return t[start:end + 1]


def _ollama_host(host: str | None = None) -> str:
    h = (host or os.getenv("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
    return h if h.startswith("http") else "http://" + h


_up = {"t": -1e9, "ok": False}


def ollama_up() -> bool:
    """Is Ollama answering? Cached 30 s so the UI's health polling doesn't probe it on every request."""
    if time.monotonic() - _up["t"] > 30:
        try:
            ok = httpx.get(f"{_ollama_host()}/api/tags", timeout=2.0).status_code == 200
        except httpx.HTTPError:
            ok = False
        _up.update(t=time.monotonic(), ok=ok)
    return _up["ok"]


class OllamaLLM(LLM):
    def __init__(self, host: str | None = None, **kw):
        kw.setdefault("model", os.getenv("FORGE_MODEL", "qwen2.5:7b"))
        kw.setdefault("judge_model", os.getenv("FORGE_JUDGE_MODEL", "llama3.1:8b"))
        kw.setdefault("embed_model", os.getenv("FORGE_EMBED_MODEL", "nomic-embed-text"))
        super().__init__(**kw)
        self.host = _ollama_host(host)
        self.http = httpx.Client(timeout=httpx.Timeout(600.0, connect=10.0))

    def _chat_raw(self, messages, model, schema, temperature):
        body = {"model": model, "messages": messages, "stream": False,
                # 4096 fits every prompt here; on CPU, prompt evaluation dominates latency, so the smaller window is ~2x faster
                "options": {"temperature": temperature, "seed": self.seed, "num_ctx": int(os.getenv("FORGE_NUM_CTX", "4096")),
                            "num_predict": 900}}
        if schema is not None:
            body["format"] = schema
        r = self.http.post(f"{self.host}/api/chat", json=body)
        if r.status_code != 200:
            raise LLMError(f"ollama {r.status_code}: {r.text[:300]}")
        d = r.json()
        return d["message"]["content"], int(d.get("prompt_eval_count", 0)) + int(d.get("eval_count", 0))

    def _embed_raw(self, texts):
        out: list[list[float]] = []
        for i in range(0, len(texts), 32):
            r = self.http.post(f"{self.host}/api/embed", json={"model": self.embed_model, "input": texts[i:i + 32]})
            if r.status_code != 200:
                raise LLMError(f"ollama embed {r.status_code}: {r.text[:300]}")
            out.extend(r.json()["embeddings"])
        return out

    def health(self) -> dict:
        """Which configured models are actually pulled. Used by CLI/UI preflight."""
        try:
            tags = {m["name"] for m in self.http.get(f"{self.host}/api/tags").json().get("models", [])}
        except httpx.HTTPError as e:
            return {"ok": False, "error": f"Ollama not reachable at {self.host}: {e}", "provider": "ollama"}

        def has(m):  # bare names match ":latest"
            return m in tags or f"{m}:latest" in tags
        need = {"model": self.model, "judge_model": self.judge_model, "embed_model": self.embed_model}
        missing = {k: v for k, v in need.items() if v and not has(v)}
        return {"ok": not missing, "missing": missing, "available": sorted(tags), "provider": "ollama"}


class GroqLLM(LLM):
    """Groq's OpenAI-compatible API serving open-weight models. Same tracing, budget and schema-retry as Ollama.

    Groq has no embedding endpoint: retrieval falls back to BM25 unless FORGE_EMBED_VIA_OLLAMA=1, which keeps
    nomic-embed-text on a local Ollama for hybrid search. The key is read from GROQ_API_KEY and never logged."""

    URL = "https://api.groq.com/openai/v1"
    MODEL, JUDGE = "openai/gpt-oss-20b", "qwen/qwen3.8-27b"  # different families: limits self-preference

    def __init__(self, api_key: str | None = None, **kw):
        kw.setdefault("model", os.getenv("FORGE_MODEL", self.MODEL))
        kw.setdefault("judge_model", os.getenv("FORGE_JUDGE_MODEL", self.JUDGE))
        # a run built with embeddings keeps them, but only while Ollama is up; otherwise retrieval drops to BM25
        via_ollama = (os.getenv("FORGE_EMBED_VIA_OLLAMA") == "1" or bool(kw.get("embed_model"))) and ollama_up()
        kw["embed_model"] = (kw.get("embed_model") or os.getenv("FORGE_EMBED_MODEL", "nomic-embed-text")) if via_ollama else None
        super().__init__(**kw)
        self.key = api_key or os.getenv("GROQ_API_KEY", "")
        self.http = httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))
        self._embedder = OllamaLLM(embed_model=self.embed_model) if via_ollama else None

    def _chat_raw(self, messages, model, schema, temperature):
        msgs = [dict(m) for m in messages]
        body = {"model": model, "messages": msgs, "temperature": temperature, "seed": self.seed, "max_tokens": 900}
        if schema is not None:
            # json_object mode needs "json" in the prompt; the schema itself is enforced by structured()'s validation
            msgs[-1]["content"] += "\n\nRespond with a single JSON object matching this JSON schema:\n" + json.dumps(schema)
            body["response_format"] = {"type": "json_object"}
        if model.startswith("qwen/qwen3"):
            body["reasoning_effort"] = "none"  # keep <think> text out of JSON answers
        elif model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"  # short hidden reasoning: fewer tokens, faster calls
        for attempt in range(6):
            r = self.http.post(f"{self.URL}/chat/completions", json=body, headers={"Authorization": f"Bearer {self.key}"})
            if r.status_code == 429 or r.status_code >= 500:  # rate limit or transient: wait as told, then retry
                wait = float(r.headers.get("retry-after") or 2 ** attempt)
                time.sleep(min(wait, 60))
                continue
            if r.status_code != 200:
                raise LLMError(f"groq {r.status_code}: {r.text[:300]}")
            d = r.json()
            return d["choices"][0]["message"]["content"] or "", int(d.get("usage", {}).get("total_tokens", 0))
        raise LLMError("groq: still rate-limited after 6 retries")

    def _embed_raw(self, texts):
        if not self._embedder:
            raise LLMError("Groq has no embeddings; set FORGE_EMBED_VIA_OLLAMA=1 for hybrid retrieval")
        return self._embedder._embed_raw(texts)

    def health(self) -> dict:
        if not self.key:
            return {"ok": False, "error": "GROQ_API_KEY is not set", "provider": "groq"}
        try:
            r = self.http.get(f"{self.URL}/models", headers={"Authorization": f"Bearer {self.key}"})
        except httpx.HTTPError as e:
            return {"ok": False, "error": f"Groq not reachable: {e}", "provider": "groq"}
        if r.status_code != 200:
            return {"ok": False, "error": f"Groq rejected the key or request ({r.status_code})", "provider": "groq"}
        have = {m["id"] for m in r.json().get("data", [])}
        missing = {k: v for k, v in {"model": self.model, "judge_model": self.judge_model}.items() if v not in have}
        out = {"ok": not missing, "missing": missing, "provider": "groq"}
        if self._embedder:
            eh = self._embedder.health()
            if not eh.get("ok"):
                out.update(ok=False, error=f"embeddings via Ollama unavailable: {eh.get('error') or eh.get('missing')}")
        return out


def make_llm(provider: str | None = None, **kw) -> LLM:
    """FORGE_PROVIDER=groq|ollama (default ollama). Every entry point builds its model client through here.

    Groq takes over whenever Ollama is asked for but not reachable and GROQ_API_KEY is set (e.g. on a host
    with no GPU): Ollama model tags mean nothing on Groq, so the Groq defaults are used instead."""
    p = (provider or os.getenv("FORGE_PROVIDER", "ollama")).lower()
    if p == "ollama" and os.getenv("GROQ_API_KEY") and not ollama_up():
        rest = {k: v for k, v in kw.items() if k not in ("model", "judge_model", "embed_model")}
        return GroqLLM(model=GroqLLM.MODEL, judge_model=GroqLLM.JUDGE, **rest)
    if p == "groq":
        return GroqLLM(**kw)
    if p == "ollama":
        return OllamaLLM(**kw)
    raise ValueError(f"unknown FORGE_PROVIDER {p!r} (use 'ollama' or 'groq')")
