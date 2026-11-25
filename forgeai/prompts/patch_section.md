You are fixing ONE section of an assistant's system prompt. Do not rewrite the whole prompt.

FAILURE CATEGORY: $category
WHAT THAT MEANS: $meaning

CURRENT SECTION ($section):
$current

FAILED TEST CASES:
$failures

Write the revised section. Keep everything that is still correct; change or add only what addresses these
failures. Write general rules, not answers to these specific questions. Keep it under $max_chars characters.
In "rationale", write one sentence of your own saying what you changed and which failure it addresses.
Return JSON: {"new_text": "...", "rationale": "..."}
