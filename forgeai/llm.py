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


class OllamaLLM(LLM):
    def __init__(self, host: str | None = None, **kw):
        kw.setdefault("model", os.getenv("FORGE_MODEL", "qwen2.5:7b"))
        kw.setdefault("judge_model", os.getenv("FORGE_JUDGE_MODEL", "llama3.1:8b"))
        kw.setdefault("embed_model", os.getenv("FORGE_EMBED_MODEL", "nomic-embed-text"))
        super().__init__(**kw)
        self.host = (host or os.getenv("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        if not self.host.startswith("http"):
            self.host = "http://" + self.host
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
            return {"ok": False, "error": f"Ollama not reachable at {self.host}: {e}"}

        def has(m):  # bare names match ":latest"
            return m in tags or f"{m}:latest" in tags
        need = {"model": self.model, "judge_model": self.judge_model, "embed_model": self.embed_model}
        missing = {k: v for k, v in need.items() if v and not has(v)}
        return {"ok": not missing, "missing": missing, "available": sorted(tags)}
