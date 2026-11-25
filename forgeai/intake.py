"""Intake interviewer (req 1) + groundability guard (req 2)."""
from __future__ import annotations

from typing import Callable

from .ingest import Document
from .llm import LLM, LLMError
from .promptlib import P
from .retrieval import Index
from .schemas import QA, ClarifyingQuestions, GeneratedQuestions, GroundCheck, GroundVerdict, Requirements, RequirementsDraft
from .textmatch import GENERIC_STEMS as _GENERIC
from .textmatch import fact_in
from .textmatch import stems as _stems
from .tools import REGISTRY


def doc_overview(docs: list[Document]) -> str:
    lines = []
    for d in docs:
        if d.kind == "csv":
            cols = list(d.rows[0].keys()) if d.rows else []
            lines.append(f"- {d.id} (csv, {len(d.rows)} rows, columns: {', '.join(cols)})")
        else:
            head = " ".join(d.text.split())[:300]
            lines.append(f"- {d.id} ({d.kind}, {len(d.text)} chars): {head}...")
    return "\n".join(lines) or "(no documents)"


def interview(brief: str, docs: list[Document], llm: LLM, answers: list[str] | None = None,
              ask: Callable[[str], str] | None = None) -> list[QA]:
    """At most 5 questions. A human answers via `ask` (CLI/UI) or `answers`; otherwise defaults are ASSUMED and labelled."""
    qs = llm.structured(P("intake_questions", brief=brief, doc_overview=doc_overview(docs)), ClarifyingQuestions).questions
    qs = [q.strip() for q in qs if q.strip()][:5]
    out: list[QA] = []
    if ask:
        for q in qs:
            a = ask(q).strip()
            out.append(QA(question=q, answer=a or "No answer given; use a conservative default.", assumed=not a))
        return out
    if answers:
        return [QA(question=q, answer=a) for q, a in zip(qs, answers)] + \
               [QA(question=q, answer="No answer given; use a conservative default.", assumed=True) for q in qs[len(answers):]]
    try:
        defaults = llm.structured(P("intake_assume", brief=brief, questions="\n".join(f"{i + 1}. {q}" for i, q in enumerate(qs))),
                                  GeneratedQuestions).questions
    except LLMError:
        defaults = []
    defaults += ["Use the most conservative default."] * (len(qs) - len(defaults))
    return [QA(question=q, answer=a, assumed=True) for q, a in zip(qs, defaults)]


def draft_requirements(brief: str, docs: list[Document], qa: list[QA], llm: LLM) -> RequirementsDraft:
    tools = "\n".join(f"- {n}: {s['purpose']}" for n, s in REGISTRY.items())
    clar = "\n".join(f"Q: {x.question}\nA: {x.answer}{' (assumed)' if x.assumed else ''}" for x in qa) or "(none)"
    d = llm.structured(P("intake_requirements", brief=brief, clarifications=clar, doc_overview=doc_overview(docs), tools=tools),
                       RequirementsDraft)
    d.must_answer = d.must_answer[:8]
    d.must_refuse = d.must_refuse[:8]
    return d



def ground_check(draft: RequirementsDraft, index: Index, llm: LLM, has_csv: bool) -> Requirements:
    """Every must-answer topic must be backed by a verifiable, on-topic quote or by a registered tool; otherwise it
    is moved to must_refuse and flagged, so the generated agent cannot 'hallucinate the gap away'.
    Small judges say 'supported' too easily, so two deterministic gates sit around the LLM verdict."""
    checks, flags, keep = [], [], []
    doc_vocab = set().union(*(_stems(c.text) for c in index.chunks)) if index.chunks else set()
    for t in draft.must_answer:
        hint = t.source_hint.strip().lower()
        if hint.startswith("tool:"):
            tool = hint.split(":", 1)[1].strip()
            if tool in REGISTRY and (tool != "csv_lookup" or has_csv):
                checks.append(GroundCheck(topic=t.name, status="supported", note=f"served by tool {tool}"))
                keep.append(t)
                continue
            # tool missing/unusable -> fall through to a document check
        name_stems = _stems(t.name) - _GENERIC
        topic_stems = (_stems(f"{t.name} {t.description}") - _GENERIC) or name_stems
        if name_stems and not name_stems & doc_vocab:
            # gate 1: none of the topic's own words occur anywhere in the documents -> not groundable, no LLM needed
            v = GroundVerdict(status="unsupported", note=f"none of {sorted(name_stems)} appear in any document")
            hits = []
        else:
            hits = index.search(f"{t.name}. {t.description}", k=5)
            excerpts = "\n\n".join(f"[{c.id}]\n{c.text}" for c in hits)
            try:
                v = llm.structured(P("groundability", topic=t.name, description=t.description, excerpts=excerpts or "(none)"),
                                   GroundVerdict, judge=True)
            except LLMError as e:
                v = GroundVerdict(status="partial", note=f"check failed: {e}")
        status, note = v.status, v.note
        evidence = []
        if status != "unsupported":
            src = [c for c in hits if v.quote and fact_in(v.quote, c.text, threshold=0.85)]
            if not src:  # the checker could not show its evidence -> don't trust "supported"
                status, note = "partial", f"quote could not be verified in the documents; {note}"
            elif not _stems(v.quote) & topic_stems:  # gate 2: a real quote, but about something else
                status, note = "partial", f"quoted evidence is not about this topic; {note}"
            else:
                evidence = list(dict.fromkeys(c.doc for c in src))
        checks.append(GroundCheck(topic=t.name, status=status, evidence=evidence, quote=v.quote if evidence else "", note=note))
        if status == "unsupported":
            flags.append(f"NOT GROUNDABLE: the brief asks for '{t.name}' but the documents do not cover it. "
                         f"The agent will refuse these questions instead of guessing.")
        else:
            if status == "partial":
                flags.append(f"PARTIAL COVERAGE: '{t.name}' is only partly covered; answers may be incomplete.")
            keep.append(t)
    refuse = list(draft.must_refuse) + [f"{c.topic} (requested, but not covered by the documents)"
                                        for c in checks if c.status == "unsupported"]
    data = draft.model_dump()
    data.update(must_answer=[t.model_dump() for t in keep], must_refuse=refuse)
    return Requirements(**data, groundability=checks, flags=flags)


def requirements_markdown(r: Requirements) -> str:
    md = [f"# Requirements: {r.title}", "", f"**Scope:** {r.scope}", "", f"**Audience:** {r.audience}", "",
          f"**Tone:** {r.tone}", "", "## Must answer"]
    md += [f"- **{t.name}** - {t.description} _(source: {t.source_hint})_" for t in r.must_answer]
    md += ["", "## Must refuse"] + [f"- {x}" for x in r.must_refuse]
    md += ["", "## Groundability check", "| Topic | Status | Evidence | Note |", "|---|---|---|---|"]
    md += [f"| {c.topic} | {c.status} | {', '.join(c.evidence) or '-'} | {c.note} |" for c in r.groundability]
    if r.flags:
        md += ["", "## Flags"] + [f"- {f}" for f in r.flags]
    md += ["", "## Clarifications"] + [f"- **Q:** {c.question}  \n  **A:** {c.answer}{' _(assumed - no human answer)_' if c.assumed else ''}"
                                       for c in r.clarifications]
    return "\n".join(md) + "\n"


def run_intake(brief: str, docs: list[Document], index: Index, llm: LLM, answers=None, ask=None) -> Requirements:
    qa = interview(brief, docs, llm, answers, ask)
    draft = draft_requirements(brief, docs, qa, llm)
    req = ground_check(draft, index, llm, has_csv=any(d.kind == "csv" for d in docs))
    req.clarifications = qa
    return req
