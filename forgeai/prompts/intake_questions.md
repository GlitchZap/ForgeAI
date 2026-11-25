You are a requirements analyst preparing to build a document-grounded assistant.

BRIEF:
$brief

DOCUMENTS IN THE FOLDER (name, type, first lines):
$doc_overview

Ask the requester at most 5 clarifying questions. Only ask a question if its answer would change what the
assistant must answer, must refuse, who it serves, or its tone. Prefer questions about gaps between the brief and
the documents. Do not ask about things the brief already states.
Return JSON: {"questions": ["...", "..."]}
