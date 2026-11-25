Decide whether a tool call is needed before answering. Use a tool only when the excerpts cannot answer and the
tool can (live data, today's date, arithmetic, exact table lookup). Never call the same tool twice with the same args.

TOOLS:
$tools

QUESTION: $question

EXCERPTS (may already contain the answer):
$excerpts

$previous
Return JSON: {"tool": "<tool name, or none>", "args": {}}
