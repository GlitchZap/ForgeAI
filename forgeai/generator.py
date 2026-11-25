"""Agent generator (req 3): requirements + documents -> declarative AgentDefinition."""
from __future__ import annotations

import re

from .ingest import Document
from .llm import LLM, LLMError
from .promptlib import P
from .schemas import AgentDefinition, PromptDraft, PromptSections, Requirements, RetrievalConfig, ToolChoice, ToolVote
from .textmatch import content_tokens, key_stems, stems
from .tools import REGISTRY, TRIGGERS, describe


def select_tools(req: Requirements, docs: list[Document], llm: LLM, brief: str = "") -> tuple[list[ToolChoice], list[dict]]:
    """Two independent votes (agent model + judge model). Attach when at least one votes yes AND the brief or
    must-answer topics show the need (TRIGGERS), ignoring sentences about ungroundable topics.
    Hard rule: csv_lookup needs a CSV in the folder."""
    has_csv = any(d.kind == "csv" for d in docs)
    req_json = req.model_dump_json(include={"scope", "audience", "must_answer", "must_refuse"}, indent=1)
    # evidence text: the brief + must-answer topics, minus sentences about topics the documents cannot support
    gaps = set().union(*[key_stems(g.topic) for g in req.groundability if g.status == "unsupported"])
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n", brief) if not stems(s) & gaps]
    evidence_text = " ".join(sentences + [f"{t.name.replace('_', ' ')} {t.description}" for t in req.must_answer])
    chosen, log = [], []
    for name, spec in REGISTRY.items():
        if spec.get("requires_csv") and not has_csv:
            log.append({"tool": name, "attached": False, "why": "no CSV files in the document folder"})
            continue
        hinted = any(t.source_hint.strip().lower() == f"tool:{name}" for t in req.must_answer)
        votes = []
        for judge in (False, True):
            try:
                # the brief goes in verbatim: intake summaries can drop a need (e.g. "days left before a deadline")
                votes.append(llm.structured(P("tool_vote", tool=name, purpose=spec["purpose"], requirements=req_json,
                                              has_csv=has_csv, brief=brief or "(not available)"), ToolVote, judge=judge))
            except LLMError:
                pass
        yes = [v for v in votes if v.needed]
        found = sorted({m.group(0).lower() for m in re.finditer(rf"\b({TRIGGERS[name].replace(' ', r'\s+')})", evidence_text, re.I)})
        attach = bool(yes) and (bool(found) or hinted)  # a vote AND visible need in the requester's text
        log.append({"tool": name, "attached": attach, "hinted_by_requirements": hinted, "evidence_words": found,
                    "votes": [v.model_dump() for v in votes]})
        if attach:
            chosen.append(ToolChoice(name=name, reason=yes[0].reason))
    return chosen, log


def _ensure_refusals(policy: str, must_refuse: list[str]) -> str:
    """Deterministic repair: every must-refuse item must be visibly covered by the refusal policy."""
    have = set(content_tokens(policy))
    def covered(m: str) -> bool:
        toks = set(content_tokens(m))
        return bool(toks) and len(toks & have) / len(toks) >= 0.6  # "medical advice" is not covered by "legal advice"
    missing = [m for m in must_refuse if not covered(m)]
    return policy + "".join(f"\n- Decline: {m}" for m in missing)


VARIANTS = [
    "",
    "Variant style: STRICT. Make grounding and refusal rules short, explicit and absolute; answers as brief as possible.",
    "Variant style: EXPLANATORY. Ask the assistant to quote the exact clause it relies on and explain it in plain words.",
]


def draft_prompt(req: Requirements, tools: list[ToolChoice], llm: LLM, variant: int = 0) -> PromptSections:
    req_json = req.model_dump_json(include={"title", "scope", "audience", "tone", "must_answer", "must_refuse", "flags"}, indent=1)
    d = llm.structured(P("generate_agent", requirements=req_json, tools=describe([t.name for t in tools]) or "(none)",
                         variant=VARIANTS[variant % len(VARIANTS)]), PromptDraft, temperature=0.0 if variant == 0 else 0.6)
    return PromptSections(role=d.role, scope=d.scope, grounding_rules=d.grounding_rules,
                          refusal_policy=_ensure_refusals(d.refusal_policy, req.must_refuse), style=d.style,
                          tool_guidance=d.tool_guidance if tools else "")


def generate_agent(req: Requirements, docs: list[Document], llm: LLM, docs_path: str, name: str,
                   candidates: int = 1, brief: str = "") -> tuple[list[AgentDefinition], list[dict]]:
    """Returns 1..3 candidate definitions that differ only in their system prompt (prompt tournament)."""
    tools, tool_log = select_tools(req, docs, llm, brief)
    csv_share = sum(d.kind == "csv" for d in docs) / max(len(docs), 1)
    retrieval = RetrievalConfig(top_k=6 if csv_share >= 0.5 else 4)  # row-level chunks are small; fetch more of them
    out = []
    for i in range(max(1, min(candidates, len(VARIANTS)))):
        try:
            prompt = draft_prompt(req, tools, llm, i)
        except LLMError:
            if i == 0:
                raise
            continue
        out.append(AgentDefinition(name=name, docs_path=docs_path, prompt=prompt, retrieval=retrieval.model_copy(),
                                   tools=tools, must_refuse=req.must_refuse))
    return out, tool_log
