# ForgeAI report: HR policy assistant

**Final agent:** v0  |  **dev pass:** 68% (19 cases)  |  **holdout pass:** 88% (8 cases, never used to tune)  |  **overall:** 74%

Stopped because: early stop - two iterations in a row bought no dev improvement. Models: agent `qwen2.5:3b`, judge `llama3.2:3b`, embeddings `nomic-embed-text` (retrieval mode: hybrid). 348 LLM calls, 287,627 tokens, 1298.0 s.

## How much to trust these numbers
- dev: 13/19 passed; 95% interval 46%-85%.
- holdout: 7/8 passed; 95% interval 53%-98%.
- overall: 20/27 passed; 95% interval 55%-87%.
- Retrieval recall@4 (all expected source documents retrieved): 23/23 = 100%.
- LLM-judge position-swap disagreement: 25% of the 12 answers the LLM judge graded (only facts credited by both orderings count; answers that passed on deterministic checks alone skip the LLM judge).
- 27 generated cases kept; 9 rejected by validators: 3 question is not about the facts from both documents; 3 labelled must-refuse but names a must-answer topic; 2 multi-doc case lacks a verified fact from each document; 1 does not actually need current_date. Kept cases can still be imperfect (see failures below).
- 5 clarifying question(s) had no human answer; conservative defaults were assumed (see requirements.md).

## Requirement flags (groundability guard)
- NOT GROUNDABLE: the brief asks for 'tax_deductions' but the documents do not cover it. The agent will refuse these questions instead of guessing.
- PARTIAL COVERAGE: 'termination_and_separation' is only partly covered; answers may be incomplete.

## Prompt tournament (dev cases only)
| Candidate | Variant | Dev pass | Prompt chars | Tokens |
|---|---|---|---|---|
| 0 **winner** | default | 68% | 1495 | 41,752 |
| 1 | Variant style: STRICT. Make grounding and refusal rules shor | 63% | 1821 | 43,310 |

Ties go to the shorter prompt. Holdout cases were not used to pick the winner.

## Per-iteration scorecard
| Iter | Dev | Holdout | Overall | Failures (all splits) | Judge disagreement | Tokens | Seconds |
|---|---|---|---|---|---|---|---|
| 0 | 68% | 88% | 74% | hallucination: 1, prompt_defect: 3, wrong_refusal: 3 | 25% | 49,624 | 148.3 |
| 1 | 68% | 88% | 74% | hallucination: 1, prompt_defect: 4, wrong_refusal: 2 | 25% | 63,748 | 281.6 |
| 2 | 68% | 88% | 74% | prompt_defect: 4, wrong_refusal: 3 | 15% | 60,989 | 250.4 |

Pass rate by case type (final): ambiguous 33%, answerable 79%, multi_doc 100%, out_of_scope 100%, tool 0%

## Changes made
### Iteration 1: wrong_refusal -> `prompt.refusal_policy` (REVERTED)
- Why: Changed the last bullet point to cover any information not covered in the provided documents, addressing the refusal of answerable questions in the test cases. | fixed: none | newly failing: none
- Addressed cases: ans-21, ans-26, ans-27
- Dev score: 68% -> 68%
<details><summary>Before / after</summary>

```
- Requests for advice on personal or confidential matters. - Requests for termination or separation policies that are not covered in the provided documents. - Requests for tax deduction information that is not covered in the provided documents. - Requests for performance evaluation or benefits information that is not covered in the provided documents. - Requests for weather or forecast information. - Requests for calculations or arithmetic not covered in the provided documents. - tax_deductions (requested, but not covered by the documents).
```
```
- Requests for advice on personal or confidential matters. - Requests for termination or separation policies that are not covered in the provided documents. - Requests for tax deduction information that is not covered in the provided documents. - Requests for performance evaluation or benefits information that is not covered in the provided documents. - Requests for weather or forecast information. - Requests for calculations or arithmetic not covered in the provided documents. - Requests for any information not covered in the provided documents.
- Decline: tax_deductions (requested, but not covered by the documents)
```
</details>

### Iteration 2: prompt_defect -> `prompt.style` (REVERTED)
- Why: I changed the section to include a general rule for using the provided policy and current_date tool, addressing the failures of missing expected facts and expected tool usage. | fixed: none | newly failing: none
- Addressed cases: amb-14, too-20
- Dev score: 68% -> 68%
<details><summary>Before / after</summary>

```
The assistant should be friendly but precise, with a focus on providing accurate and relevant information to shore staff.
```
```
The assistant should be precise and provide accurate information. They should use the provided policy and current_date tool where applicable. For example, when answering questions about leave policies, they should include all relevant facts and use the current_date tool to determine pay in lieu of notice entitlements based on the current date. For questions about notice periods, they should specify the exact notice periods for different grades as provided in the policy.
```
</details>

## What still fails (7 of 27)
- **ans-04** [answerable, dev] My manager wants me to work from home for a month, but I have a 24x7 duty roster. Can I do that?
  - Category: hallucination - the agent stated something its excerpts do not support
  - Evidence: unsupported claims: 1. You can work from home for a month.
- **amb-14** [ambiguous, dev] Can employees take 5 days off without notice?
  - Category: prompt_defect - the agent saw the right material but answered out of scope, missed key facts, or skipped the tool
  - Evidence: judge passes disagreed (position-swap); missing expected facts (recall 0.00)
- **amb-16** [ambiguous, holdout] can i book premium economy on short flights
  - Category: prompt_defect - the agent saw the right material but answered out of scope, missed key facts, or skipped the tool
  - Evidence: judge passes disagreed (position-swap); missing expected facts (recall 0.00)
- **too-20** [tool, dev] How many days' pay in lieu of notice is an employee entitled to if they leave the company without adequate notice?
  - Category: prompt_defect - the agent saw the right material but answered out of scope, missed key facts, or skipped the tool
  - Evidence: expected tool current_date, called none
- **ans-21** [answerable, dev] If I need to take a public holiday off, how many days can I carry forward from previous years?
  - Category: wrong_refusal - the answer was in the retrieved excerpts but the agent declined
  - Evidence: refused an answerable question
- **ans-26** [answerable, dev] What is not reimbursable for travel expenses?
  - Category: wrong_refusal - the answer was in the retrieved excerpts but the agent declined
  - Evidence: refused an answerable question
- **ans-27** [answerable, dev] A shore staff member has a trip that is less than 4 nights long. What is not covered?
  - Category: wrong_refusal - the answer was in the retrieved excerpts but the agent declined
  - Evidence: refused an answerable question

## Tool selection
- **csv_lookup**: not attached - no CSV files in the document folder
- **calculator**: not attached - evidence in brief: none, so votes alone are not enough (votes: yes: tax_deductions (requested, but not covered by the documents); yes: calculations or arithmetic not covered in the provided documents)
- **weather**: not attached - evidence in brief: none, so votes alone are not enough (votes: yes: weather (3-day forecast for a named place); yes: weather - Live weather and 3-day forecast for a named place (open-meteo) is not needed for this brief as it is not mentioned in the must-answer topics.)
- **current_date**: ATTACHED - evidence in brief: deadline, how many days (votes: yes: current_date - The assistant needs this tool to answer questions about 'how many days until' a deadline, as mentioned in the must-answer topics.; yes: leave_policy)

## Artifacts
requirements.md/json, agent.json (final), agent_v*.json (every version), evalset.json, scorecards.json, iteration_log.json, tool_selection.json, evalgen_log.json, trace.jsonl (every LLM call), events.jsonl
