Write a structured requirements document for a document-grounded assistant.

BRIEF:
$brief

CLARIFICATIONS (question -> answer):
$clarifications

DOCUMENTS (name, type, first lines):
$doc_overview

AVAILABLE TOOLS (only relevant if a topic truly needs live data, arithmetic, dates or exact table lookup):
$tools

Rules:
- must_answer: 3-8 topics the assistant must handle. Each topic has a short name, a one-sentence description,
  and source_hint = "documents", or "tool:<tool_name>" when only a tool can supply the answer.
- Include every topic the BRIEF asks for, even if the documents may not cover it. A later check verifies coverage.
- must_refuse: 3-6 kinds of questions the assistant must decline (out of scope, advice it must not give,
  personal or confidential data, topics nobody asked for).
- scope: two sentences. audience: who asks. tone: how it should sound.
Return JSON matching the schema.
