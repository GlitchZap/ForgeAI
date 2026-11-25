A requirements document for an assistant is below. Decide whether the assistant NEEDS this tool.
A tool is needed only if at least one must-answer topic, or something the requester explicitly asks for in the
brief, cannot be answered without it. Attaching an unneeded tool is a defect; leaving out a tool the brief
clearly needs is also a defect.

TOOL: $tool - $purpose

ORIGINAL BRIEF (the requester's own words):
$brief

REQUIREMENTS:
$requirements

DOCUMENT FOLDER CONTAINS CSV FILES: $has_csv

Return JSON: {"needed": true or false, "reason": "name the must-answer topic that needs it, or say why not"}
