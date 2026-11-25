You are grading an assistant's answer. Be strict and literal. Length and confidence earn no credit.

CONTEXT THE ASSISTANT WAS GIVEN:
$context

QUESTION: $question

ANSWER:
$answer

EXPECTED FACTS (numbered):
$facts

1. facts_present: for each expected fact, in the numbered order, true only if the answer states that fact
   (same meaning, wording may differ). Return exactly $nfacts booleans.
2. unsupported_claims: list every specific claim in the answer (numbers, dates, names, rules) that is NOT
   supported by the context. Empty list if all claims are supported. Polite filler is not a claim.
Return JSON: {"facts_present": [...], "unsupported_claims": [...]}
