# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- **Primary: OceanAI reviewers at a live demo.** Interviewers watch ForgeAI run unattended on a brief and document folder they chose and the candidate has never seen. Shown on a projector or big screen (1366x768 to 1920x1080), viewed from across a room. Their job: see that the factory works on unseen input and decide whether its numbers can be trusted.
- **Secondary: an engineer auditing a run** at a desk, digging into why a case failed and what each fix changed.

## Product Purpose
ForgeAI turns a one-paragraph brief plus a folder of documents into a working, tested chatbot agent, then reports honestly on how good it is. The web UI makes that process and its evidence legible: progress during a 15-25 minute run, the requirements and their gaps, the generated tests, the grading, every fix (kept or reverted), and what still fails. Success: a reviewer can say what the score is, whether to trust it, and why a given case failed, from the screen alone.

## Positioning
The factory distrusts itself: groundability gates, verbatim-verified test facts, position-swapped judging, dev/holdout split, keep-only-if-it-improves fixes, confidence intervals. The UI's job is to show that evidence, not to make the number look good. "A factory that explains its 78% is hired."

## Operating Context
- Runs take ~17-24 min on the target laptop (RTX 3050 4 GB, 3B local models). Progress events arrive in bursts with silent gaps up to ~3 min (agent drafting, test writing); the prompt tournament is the longest stage (6-10 min).
- Run data lives in `runs/<id>/`: events.jsonl, trace.jsonl (every LLM call), requirements, agent versions, evalset, scorecards, iteration_log, tool_selection, report.md.
- The hosted copy is read-only (FORGE_READONLY=1): saved runs only.

## Capabilities and Constraints
- Stack in place: React 19, Vite, Tailwind v4, shadcn/ui, react-three-fiber/drei, Recharts, served by FastAPI (`forgeai/server.py`).
- Per-case traces (retrieved chunks, tool calls, both judge passes) are not yet stored in scorecards; showing them needs a backend change.
- Reviewer laptops/projectors may have only an integrated GPU.

## Brand Commitments
- Name: ForgeAI. Demo company in the data is fictional (Meridian Marine Services); OceanAI is the reviewing company and must not be impersonated or branded on the UI.

## Evidence on Hand
- Real runs: `runs/hr_policy` (74% overall), `runs/ship_spares` (77%), held-out runs in progress. No testimonials, users or benchmarks exist; none may be invented.

## Product Principles
1. Evidence before score: every number is one click from the cases and traces behind it.
2. Honest by default: failures, reverted fixes, intervals and judge disagreement are shown as prominently as passes.
3. Legible from across a room during a live run; dense detail only on demand.
4. The waiting is part of the demo: long model calls must still show what is happening.

## Accessibility & Inclusion
Projector legibility (large type, high contrast, no meaning carried by color alone), keyboard navigation, reduced-motion respected.
