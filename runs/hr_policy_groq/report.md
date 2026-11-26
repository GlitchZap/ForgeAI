# ForgeAI report: HR policy (Groq)

**Final agent:** v0  |  **dev pass:** 88% (17 cases)  |  **holdout pass:** 75% (8 cases, never used to tune)  |  **overall:** 84%

Stopped because: no applicable fix left. Models: agent `openai/gpt-oss-20b`, judge `qwen/qwen3.8-27b`, embeddings `nomic-embed-text` (retrieval mode: hybrid). 268 LLM calls, 257,671 tokens, 1479.4 s.

## How much to trust these numbers
- dev: 15/17 passed; 95% interval 66%-97%.
- holdout: 6/8 passed; 95% interval 41%-93%.
- overall: 21/25 passed; 95% interval 65%-94%.
- Retrieval recall@4 (all expected source documents retrieved): 18/18 = 100%.
- LLM-judge position-swap disagreement: 12% of the 8 answers the LLM judge graded (only facts credited by both orderings count; answers that passed on deterministic checks alone skip the LLM judge).
- 25 generated cases kept; 4 rejected by validators: 2 labelled must-refuse but names a must-answer topic; 1 multi-doc case lacks a verified fact from each document; 1 does not actually need calculator. Kept cases can still be imperfect (see failures below).
- 5 clarifying question(s) had no human answer; conservative defaults were assumed (see requirements.md).

## Requirement flags (groundability guard)
- PARTIAL COVERAGE: 'Leave Balances' is only partly covered; answers may be incomplete.
- PARTIAL COVERAGE: 'Work‑From‑Home Rules' is only partly covered; answers may be incomplete.
- PARTIAL COVERAGE: 'Travel & Expense Claims' is only partly covered; answers may be incomplete.
- NOT GROUNDABLE: the brief asks for 'Tax Deduction Overview' but the documents do not cover it. The agent will refuse these questions instead of guessing.
- PARTIAL COVERAGE: 'Probation & Separation Policies' is only partly covered; answers may be incomplete.

## Prompt tournament (dev cases only)
| Candidate | Variant | Dev pass | Prompt chars | Tokens |
|---|---|---|---|---|
| 0 | default | 88% | 1419 | 39,440 |
| 1 **winner** | Variant style: STRICT. Make grounding and refusal rules shor | 88% | 1160 | 35,915 |
| 2 | Variant style: EXPLANATORY. Ask the assistant to quote the e | 88% | 1501 | 37,044 |

Ties go to the shorter prompt. Holdout cases were not used to pick the winner.

## Per-iteration scorecard
| Iter | Dev | Holdout | Overall | Failures (all splits) | Judge disagreement | Tokens | Seconds |
|---|---|---|---|---|---|---|---|
| 0 | 88% | 75% | 84% | hallucination: 1, prompt_defect: 2, wrong_refusal: 1 | 12% | 56,857 | 350.3 |
| 1 | 88% | 75% | 84% | hallucination: 1, prompt_defect: 2, wrong_refusal: 1 | 0% | 61,447 | 328.0 |

Pass rate by case type (final): ambiguous 100%, answerable 100%, multi_doc 67%, out_of_scope 100%, tool 0%

## Changes made
### Iteration 1: prompt_defect -> `prompt.tool_guidance` (REVERTED)
- Why: Added explicit rule to use current_date for date-related queries, fixing failures where no tool was called. | fixed: none | newly failing: none
- Addressed cases: too-24, too-25
- Dev score: 88% -> 88%
<details><summary>Before / after</summary>

```
Use calculator for arithmetic on provided numbers; use current_date to compute days until deadlines or notice periods.
```
```
Use the current_date tool to obtain today’s date before performing any date calculations. For arithmetic on provided numbers, use the calculator tool. Do not call any tool unless the question explicitly requires a date or numeric computation. If a question involves notice periods or deadlines, first retrieve today’s date with current_date, then use calculator for days_between or date_add as needed.
```
</details>

## What still fails (4 of 25)
- **mul-13** [multi_doc, holdout] If a Shore staff member takes parental leave and is assigned to stay on board a vessel during that period, how does the daily allowance change compared to the standard domestic rate?
  - Category: hallucination - the agent stated something its excerpts do not support
  - Evidence: numbers not in context: ['1000']
- **too-23** [tool, holdout] My hourly rate is $25.00 and I worked 37.5 hours last week. What is my total gross pay for that week?
  - Category: wrong_refusal - the answer was in the retrieved excerpts but the agent declined
  - Evidence: n/a
- **too-24** [tool, dev] I submitted my resignation notice 30 days ago, but I'm not sure if my final working day has passed yet. How many days are left in my notice period today?
  - Category: prompt_defect - the agent saw the right material but answered out of scope, missed key facts, or skipped the tool
  - Evidence: expected tool current_date, called none
- **too-25** [tool, dev] The HR policy states I must give 2 weeks' notice before leaving. If I want to leave on the 15th of next month, what is the latest date I can submit my notice to meet the requirement?
  - Category: prompt_defect - the agent saw the right material but answered out of scope, missed key facts, or skipped the tool
  - Evidence: expected tool current_date, called none

## Tool selection
- **csv_lookup**: not attached - no CSV files in the document folder
- **calculator**: ATTACHED - evidence in brief: calculat (votes: yes: Deadline Countdown; no: The 'Deadline Countdown' topic, which requires calculating days remaining, is explicitly assigned to the 'tool:current_date' in the requirements. The 'Leave Balances' topic involves retrieving data from documents rather than performing arithmetic on user-provided numbers for totals or pro-rating. Tax calculations are listed under 'must_refuse', so no arithmetic tool is needed for that. Therefore, the calculator tool is not required for any must-answer topic.)
- **weather**: not attached - evidence in brief: none, so votes alone are not enough (votes: no: No must-answer topic requires weather data; no: The brief and requirements do not mention any need for weather information. The must-answer topics focus on HR policies (leave, WFH, expenses, notice periods) and date calculations, none of which require live weather data.)
- **current_date**: ATTACHED - evidence in brief: countdown, date, deadline, expir, how many days (votes: yes: Deadline Countdown; yes: The must-answer topic 'Deadline Countdown' explicitly requires calculating how many days remain until a specified deadline, which necessitates knowing the current date. The source_hint for this topic also explicitly lists 'tool:current_date'.)

## Artifacts
requirements.md/json, agent.json (final), agent_v*.json (every version), evalset.json, scorecards.json, iteration_log.json, tool_selection.json, evalgen_log.json, trace.jsonl (every LLM call), events.jsonl
