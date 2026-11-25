"""Generic runner: loads ANY agent definition and answers questions with it (requirement 8)."""
from __future__ import annotations

import json

from .ingest import Document, chunk_documents, load_folder
from .llm import LLM, LLMError
from .promptlib import P
from .retrieval import Index
from .schemas import AgentDefinition, AgentReply, GeneratedQuestions, ToolCall, Trace
from .textmatch import looks_like_refusal
from .tools import build_tools, describe

CONTRACT = ("\n\n## Output format\nReply ONLY with JSON: {\"answer\": str, \"citations\": [chunk ids you used], "
            "\"refused\": bool, \"refusal_reason\": str}. Chunk ids look like 'file.pdf#3' and appear in square "
            "brackets before each excerpt.")


class AgentRuntime:
    def __init__(self, definition: AgentDefinition, llm: LLM, docs: list[Document] | None = None,
                 index: Index | None = None):
        self.d = definition
        self.llm = llm
        self.docs = docs if docs is not None else load_folder(definition.docs_path)[0]
        if index is None:
            r = definition.retrieval
            index = Index(chunk_documents(self.docs, r.chunk_size, r.chunk_overlap), llm)
        self.index = index
        self.tools = build_tools([t.name for t in definition.tools], self.docs)

    def ask(self, question: str, history: list[dict] | None = None) -> Trace:
        r = self.d.retrieval
        expansions: list[str] = []
        if r.query_expansion:
            try:
                expansions = self.llm.structured(P("query_expand", question=question), GeneratedQuestions).questions[:2]
            except LLMError:
                pass
        chunks = self.index.search(question, r.top_k, expansions)
        excerpts = "\n\n".join(f"[{c.id}]\n{c.text}" for c in chunks) or "(no excerpts found)"

        tool_calls: list[dict] = []
        for _ in range(2 if self.tools else 0):  # plan -> act -> check, at most two tool steps
            prev = "PREVIOUS TOOL RESULTS:\n" + "\n".join(f"{c['tool']}({c['args']}) -> {c['result']}" for c in tool_calls) if tool_calls else ""
            try:
                call = self.llm.structured(P("tool_decide", tools=describe(list(self.tools)), question=question,
                                             excerpts=excerpts[:3000], previous=prev), ToolCall)
            except LLMError:
                break
            if call.tool not in self.tools or any(c["tool"] == call.tool and c["args"] == call.args for c in tool_calls):
                break
            try:
                result = self.tools[call.tool](**call.args)
            except TypeError as e:
                result = f"error: bad arguments {e}"
            tool_calls.append({"tool": call.tool, "args": call.args, "result": str(result)[:1500]})

        user = f"EXCERPTS:\n{excerpts}\n\n"
        if tool_calls:
            user += "TOOL RESULTS:\n" + "\n".join(f"{c['tool']}({json.dumps(c['args'])}) -> {c['result']}" for c in tool_calls) + "\n\n"
        user += f"QUESTION: {question}"
        messages = [{"role": "system", "content": self.d.system_prompt + CONTRACT}, *(history or [])[-6:],
                    {"role": "user", "content": user}]
        try:
            reply = self.llm.structured(messages, AgentReply)
        except LLMError as e:
            reply = AgentReply(answer=f"[agent error: {e}]", refused=True, refusal_reason="output contract violated")

        # contract enforcement: citations must point at chunks the agent was actually shown
        shown = {c.id for c in chunks}
        reply.citations = [c for c in dict.fromkeys(reply.citations) if c in shown]
        if not reply.refused and looks_like_refusal(reply.answer) and len(reply.answer) < 300:
            reply.refused = True
        if r.require_citation and not reply.refused and not reply.citations and not tool_calls:
            reply = AgentReply(answer="I couldn't find this in the documents I have, so I won't guess.",
                               refused=True, refusal_reason="no citable evidence (require_citation)")
        return Trace(question=question, retrieved=[c.id for c in chunks],
                     retrieved_docs=list(dict.fromkeys(c.doc for c in chunks)), tool_calls=tool_calls, reply=reply)

    def context_text(self, trace: Trace) -> str:
        parts = [self.index.by_id[c].text for c in trace.retrieved if c in self.index.by_id]
        parts += [f"{c['tool']} -> {c['result']}" for c in trace.tool_calls]
        return "\n\n".join(parts)
