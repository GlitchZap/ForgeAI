"""FakeLLM: deterministic stand-in so the factory's logic is testable without Ollama.
It routes on the requested output schema and reads the prompt like a (very literal) model would."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]

from forgeai.llm import LLM  # noqa: E402


def _excerpt(text: str, marker: str = "EXCERPT") -> str:
    m = re.search(marker + r"[^\n]*:\n(.*?)(\n\n[A-Z ]+:|\nReturn JSON|$)", text, re.S)
    return m.group(1) if m else ""


def _fact_sentence(ex: str) -> str:
    for s in re.split(r"(?<=[.;])\s+|\n", ex):
        s = re.sub(r"^\[[^\]]*\]\s*", "", s.strip())
        if re.search(r"\d", s) and len(s.split()) >= 5:
            return " ".join(s.split()[:7])
    return ""


class FakeLLM(LLM):
    def __init__(self, overrides: dict | None = None, **kw):
        super().__init__(model="fake-agent", judge_model="fake-judge", embed_model=None, **kw)
        self.overrides = overrides or {}
        self.seen: list[tuple[str, str]] = []

    def _chat_raw(self, messages, model, schema, temperature):
        title = (schema or {}).get("title", "")
        text = messages[-1]["content"]
        self.seen.append((title, text))
        if title in self.overrides:
            out = self.overrides[title](text, model)
            return (out if isinstance(out, str) else json.dumps(out)), 10
        return json.dumps(self._default(title, text)), 10

    def _default(self, title, text):
        if title == "ClarifyingQuestions":
            return {"questions": ["Is the assistant for shore staff only?", "Should it cover crew?"]}
        if title == "GeneratedQuestions":
            return {"questions": ["What will the weather be on Mars tomorrow?", "Can you calculate my income tax?",
                                  "Who won the 1983 cricket world cup?", "Write me a poem about ships.",
                                  "What is my colleague's salary?", "Recommend a good stock to buy."]}
        if title == "RequirementsDraft":
            return {"title": "HR policy assistant", "scope": "Answers leave, WFH and travel policy questions.",
                    "audience": "shore staff", "tone": "friendly, precise",
                    "must_answer": [{"name": "Annual leave", "description": "entitlement and carry forward"},
                                    {"name": "Travel claims", "description": "expense claim deadlines and limits"},
                                    {"name": "Salary tax deductions", "description": "income tax deducted from salary"}],
                    "must_refuse": ["Individual salary or tax calculations", "Legal advice"]}
        if title == "GroundVerdict":
            if "tax" in text.lower().split("excerpts:")[0]:
                return {"status": "unsupported", "quote": "", "note": "not covered"}
            ex = _excerpt(text, "EXCERPTS")
            return {"status": "supported", "quote": _fact_sentence(ex) or ex[20:60], "note": "ok"}
        if title == "ToolVote":
            return {"needed": "TOOL: current_date" in text, "reason": "deadline questions" if "TOOL: current_date" in text else "not needed"}
        if title == "PromptDraft":
            return {"role": "You are the HR policy assistant.", "scope": "- leave\n- travel", "grounding_rules": "Only use excerpts.",
                    "refusal_policy": "- Decline legal advice.", "style": "Short.", "tool_guidance": "Use current_date for deadlines."}
        if title == "GeneratedQAList":
            if "EXCERPT A" in text:
                a, b = _fact_sentence(_excerpt(text, "EXCERPT A")), _fact_sentence(_excerpt(text, "EXCERPT B"))
                words = " and ".join(" ".join(re.findall(r"[a-z]{5,}", f.lower())[:2]) for f in (a, b))
                return {"items": [{"question": f"Case {len(self.seen)}: how do {words} combine?", "key_facts": [a, b]}]}
            f = _fact_sentence(_excerpt(text))
            topic = " ".join(re.findall(r"[a-z]{5,}", f.lower())[:3]) or "general"
            return {"items": [{"question": f"Case {len(self.seen)}: what applies to {topic}?", "key_facts": [f, "INVENTED FACT 999"]}]}
        if title == "ToolCall":
            return {"tool": "none", "args": {}}
        if title == "AgentReply":
            q = text.rsplit("QUESTION:", 1)[-1].lower()
            if any(w in q for w in ("mars", "tax", "cricket", "poem", "salary", "stock")):
                return {"answer": "I'm sorry, but that is outside my scope.", "citations": [], "refused": True, "refusal_reason": "out of scope"}
            m = re.search(r"\[([^\]\s]+#\w+)\]\n(.*?)(?=\n\n\[|\n\nQUESTION|$)", text, re.S)
            return {"answer": m.group(2) if m else "unknown", "citations": [m.group(1)] if m else [], "refused": False, "refusal_reason": ""}
        if title == "JudgeOut":
            n = int(re.search(r"Return exactly (\d+) booleans", text).group(1))
            return {"facts_present": [True] * n, "unsupported_claims": []}
        if title == "SectionPatch":
            cur = re.search(r"CURRENT SECTION \([^)]*\):\n(.*?)\n\nFAILED", text, re.S)
            return {"new_text": (cur.group(1) if cur else "") + "\n- Answer only what the excerpts state.", "rationale": "tightened"}
        raise AssertionError(f"FakeLLM has no default for schema {title!r}")


@pytest.fixture
def fake():
    return FakeLLM()


@pytest.fixture
def hr_docs():
    return ROOT / "demos" / "hr_policy" / "docs"
