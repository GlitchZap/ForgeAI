# The assignment, in plain words

## What OceanAI asks for
Build **ForgeAI**: a machine that builds chatbots. You give it:
- one paragraph ("I need an assistant that answers HR policy questions for shore staff"), and
- a folder of documents (PDFs, CSVs, text).

With no human help, it must hand back a **working, tested chatbot** plus an **honest report** of how good it is.

You are not building the chatbot. You are building the factory that builds it, tests it like a QA engineer, and reports with evidence.

## The core idea
A good GenAI engineer building a chatbot by hand does this loop:
1. Ask the requester what they really need.
2. Check whether the documents can actually answer it.
3. Write the system prompt, choose retrieval settings and tools.
4. Write test questions.
5. Grade the answers.
6. Find why the failures happened, fix just that, test again.
7. Write down what still doesn't work.

ForgeAI automates that loop. The hard part: every step runs on a **small local model that makes mistakes**, so the factory must check its own work instead of trusting it ("distrust your own pipeline").

## The 9 required parts
| # | Part | Plain meaning |
|---|---|---|
| 1 | Intake | Ask at most 5 questions, write a requirements doc (scope, audience, tone, what to answer, what to refuse). |
| 2 | Groundability guard | If the brief asks for something the documents don't cover, flag it. Don't build a bot that will make it up. |
| 3 | Agent generator | Produce the bot's definition: prompt, retrieval settings, tools (only the ones needed), output format. |
| 4 | Eval generator | Auto-write 20+ test questions from the documents: answerable, must-refuse, tricky, cross-document. |
| 5 | Judge | Grade each answer automatically, and guard the grader against its known biases. |
| 6 | Fix loop | Classify each failure, make one targeted fix, re-test. Max 3 rounds, log everything. |
| 7 | Honest report | Final score and what still fails and why. "A factory that explains its 78% is hired." |
| 8 | Runnable bot | A simple chat program that loads any generated bot. |
| 9 | Two demos | Run it on two very different briefs and commit all outputs. |

## What happens at the review
They bring a brief and documents you have never seen, and ForgeAI runs unattended in front of them. So it must work on unseen input, not only on our demos.

## Bonus points (all built)
Prompt tournament, token/time budget, human approval step, factory vs hand-written bot, regression mode after documents change, web UI + hosting.

## Where each part lives in this repo
See the table in the top-level `README.md`.
