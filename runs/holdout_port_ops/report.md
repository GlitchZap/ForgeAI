# ForgeAI report: Port call planner (held-out)

**Final agent:** v1  |  **dev pass:** 83% (18 cases)  |  **holdout pass:** 100% (8 cases, never used to tune)  |  **overall:** 88%

Stopped because: iteration limit (3) reached. Models: agent `qwen2.5:3b`, judge `llama3.2:3b`, embeddings `nomic-embed-text` (retrieval mode: hybrid). 450 LLM calls, 403,198 tokens, 1933.2 s.

## How much to trust these numbers
- dev: 15/18 passed; 95% interval 61%-94%.
- holdout: 8/8 passed; 95% interval 68%-100%.
- overall: 23/26 passed; 95% interval 71%-96%.
- Retrieval recall@6 (all expected source documents retrieved): 20/20 = 100%.
- LLM-judge position-swap disagreement: 38% of the 16 answers the LLM judge graded (only facts credited by both orderings count; answers that passed on deterministic checks alone skip the LLM judge).
- 26 generated cases kept; 10 rejected by validators: 4 multi-doc case lacks a verified fact from each document; 3 labelled must-refuse but names a must-answer topic; 2 question is not about the facts from both documents; 1 does not actually need current_date. Kept cases can still be imperfect (see failures below).
- 1 clarifying question(s) had no human answer; conservative defaults were assumed (see requirements.md).

## Requirement flags (groundability guard)
- NOT GROUNDABLE: the brief asks for 'Customs Duty for Ship Stores' but the documents do not cover it. The agent will refuse these questions instead of guessing.

## Prompt tournament (dev cases only)
| Candidate | Variant | Dev pass | Prompt chars | Tokens |
|---|---|---|---|---|
| 0 | default | 78% | 1258 | 81,749 |
| 1 **winner** | Variant style: STRICT. Make grounding and refusal rules shor | 78% | 1239 | 55,162 |

Ties go to the shorter prompt. Holdout cases were not used to pick the winner.

## Per-iteration scorecard
| Iter | Dev | Holdout | Overall | Failures (all splits) | Judge disagreement | Tokens | Seconds |
|---|---|---|---|---|---|---|---|
| 0 | 78% | 100% | 85% | hallucination: 1, prompt_defect: 2, wrong_refusal: 1 | 33% | 60,503 | 247.4 |
| 1 | 83% | 100% | 88% | hallucination: 1, prompt_defect: 1, wrong_refusal: 1 | 38% | 71,627 | 310.4 |
| 2 | 33% | 25% | 31% | hallucination: 1, prompt_defect: 1, wrong_refusal: 16 | 33% | 51,829 | 73.6 |
| 3 | 78% | 100% | 85% | hallucination: 2, prompt_defect: 1, wrong_refusal: 1 | 40% | 59,355 | 144.7 |

Pass rate by case type (final): ambiguous 100%, answerable 88%, out_of_scope 100%, tool 67%

## Changes made
### Iteration 1: prompt_defect -> `prompt.style` (KEPT)
- Why: Ensured the assistant uses the correct tool for date-related questions and provides the necessary facts for regulatory questions. | fixed: ['ans-26'] | newly failing: none
- Addressed cases: too-21, ans-26
- Dev score: 78% -> 83%
<details><summary>Before / after</summary>

```
The assistant's tone is operational and concise, providing short, factual answers to ensure planners can make informed decisions quickly.
```
```
The assistant should use the current_date tool to answer questions about future dates and times. For factual questions, the assistant must recall and provide the correct information, including mandatory regulations like pilotage requirements for vessels over 200 GT. The tone should remain operational and concise, ensuring planners receive quick, accurate information.
```
</details>

### Iteration 2: hallucination -> `prompt.grounding_rules + retrieval.require_citation` (REVERTED)
- Why: Changed the section to address unsupported claims and numbers not in context, ensuring answers are derived solely from the provided documents. (+ answers without citations are now blocked) | fixed: none | newly failing: ['ans-03', 'ans-04', 'ans-05', 'ans-06', 'ans-07', 'ans-08', 'ans-11', 'ans-12', 'amb-14', 'amb-15', 'ans-22', 'ans-23', 'ans-24', 'ans-25', 'ans-26']
- Addressed cases: ans-01
- Dev score: 83% -> 33%
<details><summary>Before / after</summary>

```
Answers must be derived from the provided documents. Do not cite chunk IDs. If the answer is not found, state 'Excerpt not found' and set refused=true.
```
```
Answers must be derived from the provided documents. Do not cite chunk IDs or unsupported claims. If the answer is not found, state 'Excerpt not found' and set refused=true. If the answer involves numbers or times not in the context, state 'Excerpt not found' and set refused=true.
```
</details>

### Iteration 3: wrong_refusal -> `prompt.refusal_policy` (REVERTED)
- Why: Changed the wording to ensure consistency and clarity, addressing the failure of refusing answerable questions. | fixed: none | newly failing: ['ans-26']
- Addressed cases: ans-10
- Dev score: 83% -> 78%
<details><summary>Before / after</summary>

```
- For questions about specific port calls or regions outside the India West and South Coast, politely decline and suggest contacting a human contact (if provided in the documents).
- For requests for advice, recommendations, personal or confidential data, or detailed explanations, politely decline and suggest contacting a human contact (if provided in the documents).
- For unsupported topics such as Customs Duty for Ship Stores, politely decline and state 'Not covered in provided documents'.
- Decline: Requests for information not explicitly asked for in the brief.
```
```
- For questions about specific port calls or regions outside the India West and South Coast, politely decline and suggest contacting a human contact (if provided in the documents).
- For requests for advice, recommendations, personal or confidential data, or detailed explanations, politely decline and suggest contacting a human contact (if provided in the documents).
- For unsupported topics such as Customs Duty for Ship Stores, politely decline and state 'Not covered in provided documents'.
- For unsupported topics such as specific port calls or regions outside the India West and South Coast, politely decline and suggest contacting a human contact (if provided in the documents).
- Decline: Requests for information not explicitly asked for in the brief.
```
</details>

## What still fails (3 of 26)
- **ans-01** [answerable, dev] When contacting Coastal Line Agencies in Mangaluru, what is the best time to reach them?
  - Category: hallucination - the agent stated something its excerpts do not support
  - Evidence: unsupported claims: 92; as per the provided documents; numbers not in context: ['92']; judge passes disagreed (position-swap)
- **ans-10** [answerable, dev] If a ship arrives at Kochi port after 200 meters, what is the agent's response?
  - Category: wrong_refusal - the answer was in the retrieved excerpts but the agent declined
  - Evidence: refused an answerable question
- **too-21** [tool, dev] How many days until the next low tide at the Port of Chennai?
  - Category: prompt_defect - the agent saw the right material but answered out of scope, missed key facts, or skipped the tool
  - Evidence: expected tool current_date, called none

## Tool selection
- **csv_lookup**: not attached - evidence in brief: none, so votes alone are not enough (votes: yes: weather_forecast; yes: Weather Forecast)
- **calculator**: not attached - evidence in brief: none, so votes alone are not enough (votes: yes: Weather Forecast - This requires a tool to provide the current weather and the next few days' forecast for the port.; yes: Weather Forecast)
- **weather**: ATTACHED - evidence in brief: forecast, weather (votes: yes: weather; yes: Weather Forecast)
- **current_date**: ATTACHED - evidence in brief: due (votes: yes: current_date - for providing 'how many days until' questions related to deadlines and notice periods; yes: Weather Forecast)

## Artifacts
requirements.md/json, agent.json (final), agent_v*.json (every version), evalset.json, scorecards.json, iteration_log.json, tool_selection.json, evalgen_log.json, trace.jsonl (every LLM call), events.jsonl
