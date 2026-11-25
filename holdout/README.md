# Held-out briefs

These two brief + document sets stand in for the unseen brief OceanAI will bring to the review. They were written
together with the demos (see `demos/SYNTHESIS.md`) but are **not** run while developing or tuning ForgeAI's
prompts. Run them once, from a fresh clone, and commit whatever comes out:

```
python -m forgeai run --brief holdout/crew_it/brief.md  --docs holdout/crew_it/docs  --out runs/holdout_crew_it
python -m forgeai run --brief holdout/port_ops/brief.md --docs holdout/port_ops/docs --out runs/holdout_port_ops
```

What each one checks:
- `crew_it`: plain .txt + .md input, a short-answer audience, no tools needed, and a gap (satellite data pricing).
- `port_ops`: a brief that genuinely needs the weather tool (an HR agent with a weather tool is a defect; a port
  agent without one is too), a small contacts CSV, and a gap (customs duty).
