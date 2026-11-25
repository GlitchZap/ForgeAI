# ForgeAI - the agent that builds agents

New here? Read [docs/ASSIGNMENT_EXPLAINED.md](docs/ASSIGNMENT_EXPLAINED.md) first.

Give ForgeAI a one-paragraph brief and a folder of documents. Unattended, it:

1. **Interviews** the requester (at most 5 questions; with no human present it assumes conservative defaults and says so).
2. **Checks groundability**: every topic the brief asks for must be backed by a quote that is verifiably in the documents, or by a registered tool. Topics that fail move to *must refuse* and are flagged, so the agent cannot hallucinate the gap away.
3. **Generates a declarative agent**: a sectioned system prompt, retrieval settings, an output contract, and only the tools the brief needs (two independent model votes, plus hard rules such as "no CSV, no `csv_lookup`").
4. **Generates 20+ test cases from the documents**: answerable, two-document, ambiguous, out-of-scope and tool cases. Every expected fact must appear verbatim in its source chunk or the case is rejected. Tests are written by the *judge* model, never by the agent model, and split 70/30 into dev and holdout.
5. **Judges** each answer with deterministic checks first, then an LLM judge that is itself checked (see below).
6. **Optimizes**: every failure gets one category (retrieval miss / prompt defect / hallucination / wrong refusal). The largest category gets one targeted change to one part of the definition, the full set is re-run, and the change is **kept only if the dev score rises**. At most 3 iterations, each logged with before/after.
7. **Reports honestly**: dev vs holdout (overfitting check), judge disagreement rate, rejected test cases, assumed answers, and every remaining failure with its cause.

## Quick start

```powershell
# 1. Models (install Ollama from https://ollama.com/download)
ollama pull qwen2.5:7b          # agent + generator
ollama pull llama3.1:8b         # judge: a different model family, to limit self-preference
ollama pull nomic-embed-text    # embeddings for hybrid retrieval

# 2. Python
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m forgeai doctor          # checks Ollama and the models

# 3. Run the factory, unattended
.venv\Scripts\python -m forgeai run --brief demos/hr_policy/brief.md --docs demos/hr_policy/docs --out runs/hr_policy
.venv\Scripts\python -m forgeai chat runs/hr_policy/agent.json     # generic chat runner for any definition

# 4. Web UI
cd web; npm install; npm run build; cd ..
.venv\Scripts\python -m forgeai serve           # http://127.0.0.1:8000
```

Other models: `--model`, `--judge-model`, or env vars `FORGE_MODEL`, `FORGE_JUDGE_MODEL`, `FORGE_EMBED_MODEL`, `OLLAMA_HOST`.

**On a 4 GB GPU** (the committed runs were made on an RTX 3050 laptop): the 7-8B models only partly fit, so use the 3B pair, which runs fully on the GPU at about 8-14 s per call:
```powershell
ollama pull qwen2.5:3b; ollama pull llama3.2:3b
$env:FORGE_MODEL="qwen2.5:3b"; $env:FORGE_JUDGE_MODEL="llama3.2:3b"
```
The web UI's chat always uses the models recorded in each run's `run.json`, whatever the server's defaults.

**Web UI checks:** `cd web; npm run build; npx playwright test` runs 13 end-to-end tests against the real server and runs (including axe accessibility scans and one real chat question).

## The nine requirements, and where they live

| # | Requirement | Code | Evidence in a run folder |
|---|---|---|---|
| 1 | Intake interviewer | `forgeai/intake.py` (`interview`, `draft_requirements`) | `requirements.md/json` |
| 2 | Groundability guard | `forgeai/intake.py` (`ground_check`) | groundability table and flags in `requirements.md` |
| 3 | Agent generator | `forgeai/generator.py` | `agent_v0.json`, `tool_selection.json` |
| 4 | Eval generator | `forgeai/evalgen.py`, prompts `forgeai/prompts/evalgen_*.md` | `evalset.json`, `evalgen_log.json` (rejections) |
| 5 | Judge | `forgeai/judge.py`, `forgeai/textmatch.py` | per-case results in `scorecards.json` |
| 6 | Critic-optimizer loop | `forgeai/optimizer.py`, `forgeai/pipeline.py` | `iteration_log.json`, `agent_v*.json` |
| 7 | Honest reporting | `forgeai/report.py` | `report.md` |
| 8 | Runnable product | `forgeai/agent_runtime.py`, `python -m forgeai chat` | any `agent.json` |
| 9 | Two demonstrations | `demos/hr_policy`, `demos/ship_spares` | `runs/hr_policy`, `runs/ship_spares` |

All generation prompts are committed in `forgeai/prompts/`. The demo documents and the prompt that synthesized them are in `demos/` (see `demos/SYNTHESIS.md`). Every LLM call of a run is logged in `trace.jsonl`.

## Stretch goals

| Goal | How |
|---|---|
| Prompt tournament | `--candidates 3` (default): three prompt variants compete on **dev** cases only; ties go to the shorter prompt. Table in `report.md`, data in `tournament.json`. |
| Budget enforcement | `--budget <tokens>` / `--time-budget <seconds>`: stops early when the next iteration (estimated from the last) would not fit, and after two iterations in a row with no dev gain. Tokens and seconds per iteration are in the scorecard. |
| Human checkpoint | CLI `--approve` (edit `requirements.edit.json`, press Enter), or the UI switch "Let me approve the requirements first". |
| Factory vs human baseline | `python -m forgeai compare runs/hr_policy --baseline demos/hr_policy/human_baseline.json` writes `baseline_comparison.md`. |
| Regression mode | `python -m forgeai regress runs/hr_policy --docs demos/hr_policy/docs_v2` regenerates the agent from the saved requirements, re-runs the **old** eval set, and separates real regressions from tests made stale by the document change. |
| UI and hosting | `web/` (React, shadcn/ui, react-three-fiber) served by FastAPI. The `Dockerfile` targets Hugging Face Spaces (Docker). A free tier cannot run 7-8B models, so the hosted app shows committed runs read-only unless `OLLAMA_HOST` points at a reachable Ollama. |

## Render deployment

The repository includes `render.yaml` for a Docker-based Render web service. It keeps `FORGE_READONLY=1`, so the public deployment can safely show the committed demo runs without accepting uploaded briefs or spending model resources.

To enable live runs or chat later:

1. Deploy Ollama on a GPU-enabled server and pull `qwen2.5:7b`, `llama3.1:8b`, and `nomic-embed-text`.
2. Set `OLLAMA_HOST` in Render to the Ollama server's public HTTPS URL.
3. Set `FORGE_READONLY=0` and redeploy.

Do not expose Ollama directly to the public internet without authentication or a reverse proxy. `OLLAMA_HOST=http://localhost:11434` is only valid when Ollama runs in the same machine/container as ForgeAI.

## How the judge is defended

| Failure mode | Defence |
|---|---|
| Position bias | Two passes with the expected facts **and** the context in reversed order. A fact counts only if both passes credit it. Disagreement is reported per iteration. |
| Self-preference | Judge model differs from the agent model by default, and the report warns if not. Test cases are also written by the judge model, so the agent never sits an exam it wrote. |
| Verbosity bias | Binary per-fact rubric, no holistic score. Answers over 1500 characters are flagged. Invented numbers are caught deterministically however fluent the prose. |
| Judge inventing problems | Each "unsupported claim" is re-checked against the context; claims whose numbers and words are present are overruled. |
| Judge vs humans | `python -m forgeai label runs/x` exports 30 sampled verdicts to `human_labels.csv`; after you fill in y/n, `python -m forgeai agreement runs/x` reports agreement and Cohen's kappa. |

## Testing the factory itself

```powershell
.venv\Scripts\python -m pytest -q
```

The suite uses a deterministic `FakeLLM` (`tests/conftest.py`), so the factory's logic is checked without a model: groundability guard, tool-selection defects, judge failure classification, position-swap disagreement, false-accusation overrule, retry on broken JSON, the optimizer keeping required refusals, the full pipeline writing every artifact, the human checkpoint, the tournament, budget stop, baseline compare and regression mode.

**Held-out briefs:** `holdout/` has two brief + document sets that stand in for the unseen review brief. They are not run while tuning prompts; see `holdout/README.md`.

## Known limits

- Retrieval is BM25 + embeddings fused with RRF; no reranker. CSVs are one row per chunk, capped at 2000 rows.
- Tool use is a plan-act-check loop of at most two calls, decided through a structured prompt rather than native function calling, because small models follow a JSON schema more reliably.
- The groundability guard asks "is this topic covered?" per topic; it can miss a gap hidden inside a topic that is otherwise covered.
- Pass thresholds (fact recall ≥ 0.5 and grounded) are fixed, not calibrated per brief.
