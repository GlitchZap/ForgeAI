# ForgeAI report: Crew IT helpdesk (held-out)

**Final agent:** v1  |  **dev pass:** 71% (14 cases)  |  **holdout pass:** 50% (6 cases, never used to tune)  |  **overall:** 65%

Stopped because: iteration limit (3) reached. Models: agent `qwen2.5:3b`, judge `llama3.2:3b`, embeddings `nomic-embed-text` (retrieval mode: hybrid). 364 LLM calls, 329,003 tokens, 1464.7 s.

## How much to trust these numbers
- dev: 10/14 passed; 95% interval 45%-88%.
- holdout: 3/6 passed; 95% interval 19%-81%.
- overall: 13/20 passed; 95% interval 43%-82%.
- Retrieval recall@4 (all expected source documents retrieved): 17/17 = 100%.
- Dev beats holdout by 21%: the fixes may be overfitting the dev cases.
- LLM-judge position-swap disagreement: 62% of the 13 answers the LLM judge graded (only facts credited by both orderings count; answers that passed on deterministic checks alone skip the LLM judge).
- 20 generated cases kept; 10 rejected by validators: 5 multi-doc case lacks a verified fact from each document; 4 labelled must-refuse but names a must-answer topic; 1 does not actually need calculator. Kept cases can still be imperfect (see failures below).
- 5 clarifying question(s) had no human answer; conservative defaults were assumed (see requirements.md).

## Requirement flags (groundability guard)
- NOT GROUNDABLE: the brief asks for 'Password Resets' but the documents do not cover it. The agent will refuse these questions instead of guessing.
- PARTIAL COVERAGE: 'Ship Email Troubleshooting' is only partly covered; answers may be incomplete.

## Prompt tournament (dev cases only)
| Candidate | Variant | Dev pass | Prompt chars | Tokens |
|---|---|---|---|---|
| 0 | default | 57% | 1910 | 44,367 |
| 1 **winner** | Variant style: STRICT. Make grounding and refusal rules shor | 64% | 1610 | 40,689 |

Ties go to the shorter prompt. Holdout cases were not used to pick the winner.

## Per-iteration scorecard
| Iter | Dev | Holdout | Overall | Failures (all splits) | Judge disagreement | Tokens | Seconds |
|---|---|---|---|---|---|---|---|
| 0 | 57% | 50% | 55% | hallucination: 3, prompt_defect: 4, wrong_refusal: 2 | 82% | 54,180 | 226.9 |
| 1 | 50% | 50% | 50% | hallucination: 2, prompt_defect: 2, wrong_refusal: 6 | 50% | 52,619 | 197.7 |
| 2 | 71% | 50% | 65% | hallucination: 3, prompt_defect: 3, wrong_refusal: 1 | 62% | 61,304 | 259.9 |
| 3 | 71% | 67% | 70% | hallucination: 1, prompt_defect: 4, wrong_refusal: 1 | 64% | 46,360 | 119.9 |

Pass rate by case type (final): ambiguous 67%, answerable 69%, multi_doc 100%, out_of_scope 50%, tool 0%

## Changes made
### Iteration 1: hallucination -> `prompt.grounding_rules + retrieval.require_citation` (REVERTED)
- Why: Changed the section to address unsupported claims and provide clearer guidelines for what information is acceptable based on the provided documents. (+ answers without citations are now blocked) | fixed: ['out-13', 'ans-18', 'ans-20'] | newly failing: ['ans-07', 'ans-08', 'amb-12', 'ans-19']
- Addressed cases: ans-02, amb-10, amb-11
- Dev score: 57% -> 50%
<details><summary>Before / after</summary>

```
- Provide information only from the provided documents.
- Refuse requests for personal or confidential data, personal matters, non-IT-related issues, and information not covered in the provided documents.
- Refuse requests for detailed troubleshooting steps not covered in the provided documents.
- Refuse requests for password resets not covered in the provided documents.
```
```
- Provide information only from the provided documents.
- Refuse requests for unsupported claims not aligned with the provided documents.
- Refuse requests for personal or confidential data, personal matters, non-IT-related issues, and information not covered in the provided documents.
- Refuse requests for detailed troubleshooting steps not covered in the provided documents.
- Refuse requests for password resets not covered in the provided documents.
```
</details>

### Iteration 2: prompt_defect -> `prompt.style` (KEPT)
- Why: Changed the tone and added general rules for using tools and providing relevant facts, addressing the prompt_defect failure. | fixed: ['amb-10', 'ans-18'] | newly failing: none
- Addressed cases: too-15, ans-18
- Dev score: 57% -> 71%
<details><summary>Before / after</summary>

```
The assistant's tone will be professional and concise, ensuring the understanding and compliance with the vessel's IT policies.
```
```
The assistant's tone will be professional and concise, ensuring the understanding and compliance with the vessel's IT policies. Use the appropriate tools and provide relevant facts and instructions. For example, for the Wi-Fi data allowance, use a calculator tool. For sending large attachments via ship email, include the expected facts such as compressing photos and the maximum attachment size per message (10 MB).
```
</details>

### Iteration 3: prompt_defect -> `prompt.style` (REVERTED)
- Why: Changed the section to include general rules for using a calculator tool for data-related questions and to specify the maximum attachment size per message for attachment size questions. | fixed: ['amb-11', 'ans-20'] | newly failing: ['amb-10']
- Addressed cases: too-15
- Dev score: 71% -> 71%
<details><summary>Before / after</summary>

```
The assistant's tone will be professional and concise, ensuring the understanding and compliance with the vessel's IT policies. Use the appropriate tools and provide relevant facts and instructions. For example, for the Wi-Fi data allowance, use a calculator tool. For sending large attachments via ship email, include the expected facts such as compressing photos and the maximum attachment size per message (10 MB).
```
```
The assistant's tone will be professional and concise, ensuring understanding and compliance with the vessel's IT policies. Use the appropriate tools and provide relevant facts and instructions. For the Wi-Fi data allowance, use a calculator tool. For sending large attachments via ship email, include the expected facts such as compressing photos and the maximum attachment size per message (10 MB). For any data-related questions, use a calculator tool. For any attachment size questions, include the maximum attachment size per message (10 MB).
```
</details>

## What still fails (7 of 20)
- **ans-01** [answerable, dev] My personal laptop is trying to connect to the ship's business network, what's the issue?
  - Category: hallucination - the agent stated something its excerpts do not support
  - Evidence: unsupported claims: Please ensure your device connects to the MMS-CREW network.; judge passes disagreed (position-swap)
- **ans-02** [answerable, dev] I just got a warning that my phone's OS is no longer receiving security updates, what should I do?
  - Category: hallucination - the agent stated something its excerpts do not support
  - Evidence: unsupported claims: You should update your operating system to the latest version available to ensure security.; judge passes disagreed (position-swap)
- **ans-04** [answerable, holdout] A crew member is trying to send a large email attachment, what should they do?
  - Category: prompt_defect - the agent saw the right material but answered out of scope, missed key facts, or skipped the tool
  - Evidence: judge passes disagreed (position-swap); missing expected facts (recall 0.00)
- **amb-11** [ambiguous, dev] whats the deal w/ the 5mb limit on emails?
  - Category: hallucination - the agent stated something its excerpts do not support
  - Evidence: unsupported claims: The limit of 5 MB for emails in the MMS Mail client is to ensure that messages do not hold up the synchronization process with the shore mail server.; judge passes disagreed (position-swap)
- **out-13** [out_of_scope, holdout] Can I reset my password?
  - Category: prompt_defect - the agent saw the right material but answered out of scope, missed key facts, or skipped the tool
  - Evidence: answered an out-of-scope question
- **too-15** [tool, dev] What is the total data allowance for Wi-Fi access on our vessel for the month of March?
  - Category: prompt_defect - the agent saw the right material but answered out of scope, missed key facts, or skipped the tool
  - Evidence: expected tool calculator, called none
- **ans-20** [answerable, holdout] Can officers and ratings use different Wi-Fi networks on the vessel?
  - Category: wrong_refusal - the answer was in the retrieved excerpts but the agent declined
  - Evidence: refused an answerable question

## Tool selection
- **csv_lookup**: not attached - no CSV files in the document folder
- **calculator**: ATTACHED - evidence in brief: cost (votes: yes: Extra Satellite Data Costs needs a tool for calculating costs if the allowance is exceeded.; yes: Data Allowances)
- **weather**: not attached - evidence in brief: none, so votes alone are not enough (votes: yes: Extra Satellite Data Costs needs the weather tool for providing information on the cost of extra satellite data if their allowance is exceeded, which might be affected by weather conditions such as storms or extreme weather events that could impact satellite communication.; yes: Extra Satellite Data Costs)
- **current_date**: not attached - evidence in brief: none, so votes alone are not enough (votes: no: current_date tool is not needed based on the provided requirements and original brief.; yes: Extra Satellite Data Costs)

## Artifacts
requirements.md/json, agent.json (final), agent_v*.json (every version), evalset.json, scorecards.json, iteration_log.json, tool_selection.json, evalgen_log.json, trace.jsonl (every LLM call), events.jsonl
