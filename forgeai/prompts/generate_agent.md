You are writing the system prompt for a production assistant. It answers ONLY from retrieved document excerpts
(and tools, if attached). Write each section as plain instructions addressed to the assistant ("You ...").

REQUIREMENTS:
$requirements

ATTACHED TOOLS:
$tools

Sections:
- role: one paragraph: who the assistant is and who it serves.
- scope: what it answers, as a bullet list built from the must-answer topics.
- grounding_rules: answer only from the provided excerpts; cite chunk ids; never invent numbers, dates, names or
  policies; if the excerpts do not contain the answer, say so and set refused=true.
- refusal_policy: bullet list of what to decline (from must-refuse and unsupported topics) and how to decline
  politely in one sentence, pointing to the right human contact if the documents name one.
- style: tone and length guidance for the audience.
- tool_guidance: when to use each attached tool; empty string if no tools are attached.
$variant
Return JSON matching the schema.
